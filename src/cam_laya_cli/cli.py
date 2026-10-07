"""Agent-facing JSON CLI for deterministic policy presets. No models, no worker."""

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import MAX_BYTES, paths
from .engine import decide, validate
from .presets import OPTIONS


def encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    if len(raw) > MAX_BYTES:
        raise ValueError("request exceeds 65536 bytes")
    value = json.loads(raw, object_pairs_hook=unique)
    if isinstance(value, float) and value != value:
        raise ValueError("JSON numbers must be finite")
    return value


def emit(value):
    sys.stdout.buffer.write(encode(value))
    sys.stdout.buffer.flush()


def exit_code(result):
    return 2 if result.get("status") == "error" else 0


def input_json(name):
    if name == "-":
        return parse(sys.stdin.buffer.read(MAX_BYTES + 1))
    with Path(name).open("rb") as stream:
        return parse(stream.read(MAX_BYTES + 1))


def status():
    return {"status": "ok", "version": __version__, "presets": sorted(OPTIONS)}


def doctor():
    from .integrations import integration_status

    config, state = paths()
    return {"status": "ok", "version": __version__, "python": platform.python_version(),
            "platform": platform.platform(), "mode": "rules-only",
            "config_exists": (config / "config.json").exists(), "state_exists": state.exists(),
            "clients": {name: {"installed": bool(shutil.which(binary))}
                        for name, binary in
                        [("codex", "codex"), ("claude", "claude"), ("opencode", "opencode")]},
            "integrations": integration_status()}


def parser():
    root = argparse.ArgumentParser(prog="cam-laya-cli", description=__doc__)
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("preset", "batch"):
        command = commands.add_parser(name)
        if name == "preset":
            command.add_argument("name", choices=OPTIONS)
        command.add_argument("--input", default="-", help="JSON file or stdin; JSONL for batch")
    for name in ("status", "doctor", "benchmark"):
        command = commands.add_parser(name)
        if name == "benchmark":
            command.add_argument("--samples", type=int, default=100)
            command.add_argument("--output", type=Path)
    for name in ("install-agent", "uninstall-agent"):
        command = commands.add_parser(name)
        command.add_argument("client", choices=["codex", "claude", "opencode"])
        command.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    return root


def decision(args, value):
    if args.command == "preset":
        value = {"state": value, "preset": args.name}
    if not isinstance(value, dict):
        raise ValueError("request must be an object")
    value = dict(value)
    validate(value)
    return decide(value)


def batch(args):
    stream = sys.stdin.buffer if args.input == "-" else Path(args.input).open("rb")
    code = 0
    try:
        index = 0
        while raw := stream.readline(MAX_BYTES + 1):
            index += 1
            try:
                if len(raw) > MAX_BYTES:
                    while not raw.endswith(b"\n") and raw:
                        raw = stream.readline(MAX_BYTES + 1)
                    raise ValueError("record exceeds 65536 bytes")
                result = decision(args, parse(raw))
            except (ValueError, TypeError, RecursionError, UnicodeError):
                result = {"status": "error", "reason_code": "invalid_input", "record": index}
            emit(result)
            code = max(code, exit_code(result))
    finally:
        if stream is not sys.stdin.buffer:
            stream.close()
    return code


def main():
    args = parser().parse_args()
    try:
        if args.command == "preset":
            result = decision(args, input_json(args.input))
        elif args.command == "batch":
            raise SystemExit(batch(args))
        elif args.command in {"status", "doctor"}:
            result = status() if args.command == "status" else doctor()
        elif args.command == "benchmark":
            from .benchmark import run

            result = run(args.samples)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(encode(result))
        elif args.command in {"install-agent", "uninstall-agent"}:
            from .integrations import install, uninstall

            result = install(args.client, args.root) if args.command == "install-agent" \
                else uninstall(args.client, args.root)
        emit(result)
        raise SystemExit(exit_code(result))
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        emit({"status": "error", "reason_code": "invalid_input", "message": str(exc)[:160]})
        raise SystemExit(2) from None
