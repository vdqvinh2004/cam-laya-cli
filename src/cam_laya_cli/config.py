"""Separate configuration and pinned, shared Hugging Face checkpoints."""

import hashlib
import json
import os
import stat
from pathlib import Path

MAX_BYTES = 65536
IDLE_SECONDS = 1800
MODELS = {
    "english": ("aac6fef/laya-mlx", "20aed815fc6acde75733882e7ec0e3f28aeb9717"),
    "multilingual": ("aac6fef/laya-multilingual-mlx", "f2b4faf51023039425946074e2cf1361d2db11d5"),
    "typed-decisions": ("aac6fef/laya-typed-decisions-mlx", "f9e501c2080cc57c13d6887820329758f5351125"),
}


def paths():
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cam-laya-cli"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "cam-laya-cli"
    socket_dir = state
    if len(os.fsencode(state / "worker.sock")) >= 100:
        digest = hashlib.sha256(os.fsencode(state.absolute())).hexdigest()[:16]
        socket_dir = Path("/tmp") / f"cam-laya-cli-{os.getuid()}-{digest}"
    return config, state, socket_dir


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


def checkpoint(name, *, download=False):
    from huggingface_hub import snapshot_download

    model, revision = MODELS[name]
    return Path(snapshot_download(
        model, revision=revision, local_files_only=not download,
        allow_patterns=["model.safetensors", "rl_agent_config.json", "encoder/config.json",
                        "tokenizer/*", "mlx_config.json", "manifest.json", "LICENSE", "NOTICE"],
    ))
