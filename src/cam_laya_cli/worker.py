"""Private persistent worker; no MCP dependency or request-content logs."""

import fcntl
import json
import os
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time

from .config import IDLE_SECONDS, MAX_BYTES, paths, private_dir, read_json, write_json
from .engine import Engine, Unavailable, finite


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
    finite(value)
    return value


def encode(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()


def start_worker(state, socket_dir, deadline):
    private_dir(state)
    private_dir(socket_dir)
    with (socket_dir / "startup.lock").open("a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Unavailable("worker_start_timeout") from None
                time.sleep(.025)
        address = socket_dir / "worker.sock"
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.settimeout(.1)
                probe.connect(str(address))
                return
            except (FileNotFoundError, ConnectionRefusedError):
                pass
        child = subprocess.Popen([sys.executable, "-m", "cam_laya_cli.worker"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        threading.Thread(target=child.wait, daemon=True).start()
        while time.monotonic() < deadline:
            try:
                info = address.lstat()
                if stat.S_ISSOCK(info.st_mode) and not info.st_mode & 0o077:
                    return
            except FileNotFoundError:
                pass
            if child.poll() is not None:
                raise Unavailable("worker_start_failed")
            time.sleep(.025)
        raise Unavailable("worker_start_timeout")


class Client:
    def __init__(self, *, start=True, timeout=60):
        self.start = start
        self.timeout = timeout
        self.socket = None
        self.stream = None

    def __enter__(self):
        _, state, socket_dir = paths()
        address = socket_dir / "worker.sock"
        deadline = time.monotonic() + min(5, self.timeout)
        spawned = False
        while True:
            connection = socket.socket(socket.AF_UNIX)
            connection.settimeout(self.timeout)
            try:
                info = address.lstat()
                parent = socket_dir.lstat()
                if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or not stat.S_ISDIR(parent.st_mode)
                        or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
                    raise PermissionError("worker socket must be private and owned")
                connection.connect(str(address))
                self.socket = connection
                self.stream = connection.makefile("rwb")
                return self
            except (FileNotFoundError, ConnectionRefusedError):
                connection.close()
                if not self.start:
                    raise Unavailable("worker_not_running") from None
                if not spawned:
                    start_worker(state, socket_dir, deadline)
                    spawned = True
                if time.monotonic() >= deadline:
                    raise Unavailable("worker_start_timeout") from None
                time.sleep(0.025)
            except Exception:
                connection.close()
                raise

    def call(self, message):
        raw = encode(message)
        if len(raw) > MAX_BYTES:
            raise ValueError("request exceeds 65536 bytes including transport fields")
        self.stream.write(raw)
        self.stream.flush()
        try:
            # Full distributions can exceed input size; still bound every response.
            raw = self.stream.readline(MAX_BYTES * 16 + 1)
        except TimeoutError as exc:
            raise Unavailable("worker_timeout") from exc
        if not raw.endswith(b"\n") or len(raw) > MAX_BYTES * 16:
            raise Unavailable("invalid_worker_response")
        value = json.loads(raw)
        finite(value)
        return value

    def __exit__(self, *_):
        if self.stream:
            self.stream.close()
        if self.socket:
            self.socket.close()


def request(message, *, start=True, timeout=60):
    with Client(start=start, timeout=timeout) as client:
        result = client.call(message)
    if message.get("op") == "stop" and result.get("stopped"):
        deadline = time.monotonic() + 2
        with (paths()[2] / "worker.lock").open("a") as lock:
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(.025)
    return result


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(60)
        while self.server.running:
            try:
                raw = self.rfile.readline(MAX_BYTES + 1)
                if not raw:
                    return
                self.server.last_activity = time.monotonic()
                message = parse(raw)
                if not isinstance(message, dict):
                    raise ValueError("worker message must be an object")
                op = message.get("op")
                engine = self.server.engine
                if op == "decide":
                    result = engine.decide(message.get("request"))
                    if not message.get("details"):
                        result.pop("details", None)
                        result.pop("confidence_semantics", None)
                    with self.server.save_lock:
                        try:
                            write_json(self.server.stats_path, engine.stats())
                        except OSError:
                            result["metrics_persisted"] = False
                elif op == "warm":
                    name = message.get("model", "english")
                    if name not in self.server.models:
                        raise ValueError("warm requires an explicit checkpoint name")
                    if message.get("background") is True:
                        def warm():
                            try:
                                engine.warm(name)
                            except Exception:
                                pass  # runtime.status retains the operational error
                        threading.Thread(target=warm, daemon=True).start()
                        result = {"status": "ok", "warming": name, "background": True}
                    else:
                        result = engine.warm(name)
                elif op == "status":
                    result = {**engine.status(), "pid": os.getpid()}
                elif op == "stats":
                    result = {"status": "ok", "counts": engine.stats()}
                elif op == "stop":
                    self.server.running = False
                    result = {"status": "ok", "stopped": True}
                else:
                    raise ValueError("invalid worker operation")
            except (ValueError, TypeError, RecursionError, UnicodeError):
                result = {"status": "error", "reason_code": "invalid_input"}
            except Unavailable as exc:
                result = {"status": "unavailable", "reason_code": str(exc)}
            except (OSError, TimeoutError):
                return
            except Exception:
                result = {"status": "unavailable", "reason_code": "worker_failure"}
            try:
                response = encode(result)
                if len(response) > MAX_BYTES * 16:
                    response = encode({"status": "unavailable", "reason_code": "response_too_large"})
                self.wfile.write(response)
                self.wfile.flush()
            except OSError:
                return
            if len(raw) > MAX_BYTES:
                return


def serve():
    from .config import MODELS

    _, state, socket_dir = paths()
    private_dir(state)
    private_dir(socket_dir)
    with (socket_dir / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        address = socket_dir / "worker.sock"
        if address.exists() or address.is_symlink():
            info = address.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise PermissionError("refusing to replace an unowned or invalid socket")
            address.unlink()
        with socketserver.ThreadingUnixStreamServer(str(address), Handler) as server:
            server.daemon_threads = True
            server.timeout = 1
            server.running = True
            server.last_activity = time.monotonic()
            server.engine = Engine()
            server.models = MODELS
            server.save_lock = threading.Lock()
            server.stats_path = state / "stats.json"
            try:
                saved = read_json(server.stats_path, {})
            except (ValueError, OSError):
                saved = {}
            if isinstance(saved, dict):
                server.engine.counts.update({k: v for k, v in saved.items() if type(v) is int and v >= 0})
            address.chmod(0o600)
            write_json(state / "worker.json", {"pid": os.getpid()})
            try:
                while server.running and time.monotonic() - server.last_activity < IDLE_SECONDS:
                    server.handle_request()
            finally:
                address.unlink(missing_ok=True)
                (state / "worker.json").unlink(missing_ok=True)


if __name__ == "__main__":
    serve()
