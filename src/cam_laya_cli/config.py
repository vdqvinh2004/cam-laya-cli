"""Separate configuration; no models, no downloads, no runtime dependencies."""

import json
import os
import stat
from pathlib import Path

MAX_BYTES = 65536


def paths():
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cam-laya-cli"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "cam-laya-cli"
    return config, state


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise PermissionError("state directory must be an owned directory, not a symlink")
    path.chmod(0o700)


def write_json(path, value):
    private_dir(path.parent)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    try:
        with os.fdopen(os.open(temporary, flags, 0o600), "w") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
