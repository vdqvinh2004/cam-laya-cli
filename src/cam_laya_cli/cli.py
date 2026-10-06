"""Agent-facing JSON CLI. Model imports live only in the worker."""

import argparse
import importlib.util
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import MAX_BYTES, MODELS, checkpoint, paths, read_json, write_json
from .engine import Unavailable, validate
from .presets import OPTIONS
from .worker import Client, encode, parse, request


def emit(value):
    sys.stdout.buffer.write(encode(value))
    sys.stdout.buffer.flush()


def exit_code(result):
    return 2 if result.get("status") == "error" else 3 if result.get("status") == "unavailable" else 0


def input_json(name):
    if name == "-":
        return parse(sys.stdin.buffer.read(MAX_BYTES + 1))
    with Path(name).open("rb") as stream:
        return parse(stream.read(MAX_BYTES + 1))


def status():
    try:
        return request({"op": "status"}, start=False, timeout=1)
    except Unavailable:
        return {"status": "ok", "worker_running": False, "model_loaded": None}


def doctor():
    from .integrations import integration_status

    config, state, _ = paths()
    supported = platform.system() == "Darwin" and platform.machine() == "arm64"
    installed = importlib.util.find_spec("laya_mlx") is not None
    return {"status": "ok", "version": __version__, "python": platform.python_version(),
            "platform": platform.platform(), "supported": supported, "mlx_installed": installed,
            "config_exists": (config / "config.json").exists(), "state_exists": state.exists(),
            "worker": status(), "clients": {name: {"installed": bool(shutil.which(binary)),
            "live_verified": False} for name, binary in
            [("codex", "codex"), ("claude", "claude"), ("opencode", "opencode")]},
            "integrations": integration_status()}


def setup(models):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise Unavailable("unsupported_platform")
    if importlib.util.find_spec("laya_mlx") is None:
        raise Unavailable("mlx_extra_missing: install cam-laya-cli[mlx]")
    provisions = {}
    for name in models:
        path = checkpoint(name, download=True)
        provisions[name] = {"id": MODELS[name][0], "revision": MODELS[name][1], "path": str(path)}
    config, _, _ = paths()
    current = read_json(config / "config.json", {})
    current.setdefault("models", {}).update(provisions)
    write_json(config / "config.json", current)
    return {"status": "ok", "models": provisions, "integrations_installed": False}


def parser():
    root = argparse.ArgumentParser(prog="cam-laya-cli", description=__doc__)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("decide", "preset", "batch"):
        command = commands.add_parser(name)
        if name == "preset":
            command.add_argument("name", choices=OPTIONS)
        command.add_argument("--input", default="-", help="JSON file or stdin; JSONL for batch")
        command.add_argument("--model", choices=["auto", *MODELS])
        command.add_argument("--min-confidence", type=float)
        command.add_argument("--details", action="store_true")
        command.add_argument("--timeout", type=float, default=60)
    command = commands.add_parser("setup")
    command.add_argument("--model", choices=MODELS, action="append")
    command = commands.add_parser("warm")
    command.add_argument("--model", choices=MODELS, default="english")
    command.add_argument("--background", action="store_true")
    for name in ("status", "doctor", "stats", "stop"):
        commands.add_parser(name)
    command = commands.add_parser("benchmark")
    command.add_argument("--input", default=None, help="request JSON; defaults to local rule probe")
    command.add_argument("--samples", type=int, default=100)
    command.add_argument("--output", type=Path)
    for name in ("install-agent", "uninstall-agent"):
        command = commands.add_parser(name)
        command.add_argument("client", choices=["codex", "claude", "opencode"])
        command.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
        if name == "install-agent":
            command.add_argument("--prewarm", action="store_true")
    command = commands.add_parser("hook")
    command.add_argument("client", choices=["codex", "claude", "opencode"])
    command.add_argument("event")
    return root


def decision(args, value):
    if args.command == "preset":
        value = {"state": value, "preset": args.name}
    if not isinstance(value, dict):
        raise ValueError("request must be an object")
    value = dict(value)
    if args.model is not None:
        value["model"] = args.model
    if args.min_confidence is not None:
        value["min_confidence"] = args.min_confidence
    validate(value)
    return {"op": "decide", "request": value, "details": args.details}


def batch(args):
    stream = sys.stdin.buffer if args.input == "-" else Path(args.input).open("rb")
    code = 0
    client = None
    try:
        index = 0
        while raw := stream.readline(MAX_BYTES + 1):
            index += 1
            try:
                if len(raw) > MAX_BYTES:
                    # Drain this record in bounded chunks, preserving later input order.
                    while not raw.endswith(b"\n") and raw:
                        raw = stream.readline(MAX_BYTES + 1)
                    raise ValueError("record exceeds 65536 bytes")
                value = parse(raw)
                message = decision(args, value)
                if client is None:
                    client = Client(timeout=args.timeout).__enter__()
                result = client.call(message)
            except (ValueError, TypeError, RecursionError, UnicodeError):
                result = {"status": "error", "reason_code": "invalid_input", "record": index}
            except (Unavailable, OSError):
                result = {"status": "unavailable", "reason_code": "worker_unavailable", "record": index}
                if client:
                    client.__exit__()
                    client = None
            emit(result)
            code = max(code, exit_code(result))
    finally:
        if client:
            client.__exit__()
        if stream is not sys.stdin.buffer:
            stream.close()
    return code


def main():
    args = parser().parse_args()
    if hasattr(args, "timeout") and (not 0 < args.timeout <= 300):
        emit({"status": "error", "reason_code": "invalid_timeout"})
        raise SystemExit(2)
    try:
        if args.command in {"decide", "preset"}:
            result = request(decision(args, input_json(args.input)), timeout=args.timeout)
        elif args.command == "batch":
            raise SystemExit(batch(args))
        elif args.command == "status":
            result = status()
        elif args.command == "doctor":
            result = doctor()
        elif args.command == "setup":
            result = setup(args.model or ["english"])
        elif args.command == "warm":
            result = request({"op": "warm", "model": args.model, "background": args.background})
        elif args.command == "stats":
            try:
                result = request({"op": "stats"}, start=False, timeout=1)
            except Unavailable:
                result = {"status": "ok", "counts": read_json(paths()[1] / "stats.json", {})}
        elif args.command == "stop":
            try:
                result = request({"op": "stop"}, start=False, timeout=1)
            except Unavailable:
                result = {"status": "ok", "stopped": False}
        elif args.command in {"install-agent", "uninstall-agent"}:
            from .integrations import install, uninstall

            result = install(args.client, args.root, args.prewarm) if args.command == "install-agent" \
                else uninstall(args.client, args.root)
        elif args.command == "benchmark":
            from .benchmark import run

            value = input_json(args.input) if args.input else {
                "preset": "test_decision", "state": {"last_test_result": "failed"}}
            result = run(value, args.samples)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(encode(result))
        elif args.command == "hook":
            # Prewarm is informational, fail-open, and injects no context.
            try:
                payload = parse(sys.stdin.buffer.read(MAX_BYTES + 1))
                if isinstance(payload, dict) and args.event in {"SessionStart", "session.created"}:
                    request({"op": "warm", "background": True}, timeout=1)
            except Exception:
                pass
            emit({})
            return
        emit(result)
        raise SystemExit(exit_code(result))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        emit({"status": "error", "reason_code": "invalid_input", "message": str(exc)[:160]})
        raise SystemExit(2) from None
    except (Unavailable, OSError) as exc:
        code = str(exc) if isinstance(exc, Unavailable) else type(exc).__name__
        emit({"status": "unavailable", "reason_code": code})
        raise SystemExit(3) from None
