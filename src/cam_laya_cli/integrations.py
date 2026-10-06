"""Project-scoped, owned skills and optional prewarm-only hooks."""

import hashlib
import json
import shlex
import shutil
import sys
from importlib.resources import files
from pathlib import Path

from .config import paths, read_json, write_json

SKILLS = {"codex": ".agents/skills/cam-laya/SKILL.md",
          "claude": ".claude/skills/cam-laya/SKILL.md",
          "opencode": ".opencode/skills/cam-laya/SKILL.md"}
SETTINGS = {"codex": ".codex/hooks.json", "claude": ".claude/settings.json"}
PLUGIN = ".opencode/plugins/cam-laya-prewarm.js"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def manifest():
    value = read_json(paths()[0] / "integrations.json", {})
    if not isinstance(value, dict):
        raise ValueError("invalid integration manifest")
    return value


def key(client, root):
    return f"{client}:{root.resolve()}"


def check_path(path):
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("integration paths must not contain symlinks")


def write_asset(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".cam-laya.tmp")
    check_path(temporary)
    temporary.write_text(text)
    temporary.replace(path)


def hook_group(client):
    command = shlex.join([sys.executable, "-m", "cam_laya_cli", "hook", client, "SessionStart"])
    return {"matcher": "startup|resume|clear", "hooks": [{"type": "command", "command": command,
             "timeout": 2, "async": True}]}


def plugin_text():
    command = json.dumps([sys.executable, "-m", "cam_laya_cli", "warm", "--background"])
    return f'''// Owned by cam-laya-cli. Session warming only; no advice injection.
import {{ spawn }} from "node:child_process";
export const CamLayaPrewarm = async () => ({{
  event: async ({{ event }}) => {{
    if (event.type !== "session.created") return;
    const command = {command};
    const child = spawn(command[0], command.slice(1), {{ stdio: "ignore" }});
    child.on("error", () => {{}});
    child.unref();
  }}
}});
'''


def install(client, root, prewarm=False):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")
    owned = manifest()
    identifier = key(client, root)
    previous = owned.get(identifier, {})
    assets = {SKILLS[client]: files("cam_laya_cli").joinpath("assets/SKILL.md").read_text()}
    if prewarm and client == "opencode":
        assets[PLUGIN] = plugin_text()
    # Preflight every touched path before changing anything.
    for relative, text in assets.items():
        path = root / relative
        check_path(path)
        check_path(path.with_name(path.name + ".cam-laya.tmp"))
        if path.exists() and digest(path.read_text()) != previous.get("assets", {}).get(relative):
            raise ValueError(f"unowned or modified integration asset: {relative}")
    settings = None
    group = None
    settings_created = False
    if prewarm and client in SETTINGS:
        settings = root / SETTINGS[client]
        check_path(settings)
        check_path(settings.with_name(settings.name + ".cam-laya.bak"))
        check_path(settings.with_name(settings.name + ".cam-laya.tmp"))
        settings_created = not settings.exists()
        data = read_json(settings, {})
        if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
            raise ValueError("client settings must contain an object of hooks")
        groups = data.get("hooks", {}).get("SessionStart", [])
        if not isinstance(groups, list):
            raise ValueError("SessionStart hooks must be a list")
        group = hook_group(client)
        old_group = previous.get("hook")
        if old_group:
            groups = [item for item in groups if item != old_group]
        if group not in groups:
            groups.append(group)
        data.setdefault("hooks", {})["SessionStart"] = groups
    record = {**previous, "client": client, "root": str(root),
              "assets": dict(previous.get("assets", {}))}
    for relative, text in assets.items():
        write_asset(root / relative, text)
        record["assets"][relative] = digest(text)
    if settings:
        backup = settings.with_name(settings.name + ".cam-laya.bak")
        check_path(backup)
        if settings.exists() and not backup.exists():
            shutil.copy2(settings, backup)
        write_asset(settings, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        record["hook"] = group
        record["settings"] = SETTINGS[client]
        record.setdefault("settings_created", settings_created)
    owned[identifier] = record
    write_json(paths()[0] / "integrations.json", owned)
    return {"status": "ok", "client": client, "root": str(root),
            "prewarm": bool(record.get("hook") or PLUGIN in record["assets"]),
            "verification": "configured_unverified", "live_verified": False}


def uninstall(client, root):
    root = root.resolve()
    owned = manifest()
    identifier = key(client, root)
    record = owned.get(identifier)
    if not record:
        return {"status": "ok", "removed": [], "kept": []}
    removed, kept = [], []
    remaining = dict(record)
    remaining["assets"] = dict(record.get("assets", {}))
    for relative in record.get("assets", {}):
        check_path(root / relative)
    if record.get("hook"):
        check_path(root / record["settings"])
    for relative, expected in record.get("assets", {}).items():
        path = root / relative
        check_path(path)
        if not path.exists():
            remaining["assets"].pop(relative)
        elif digest(path.read_text()) == expected:
            path.unlink()
            remaining["assets"].pop(relative)
            removed.append(relative)
        else:
            kept.append(relative)
    if record.get("hook"):
        settings = root / record["settings"]
        check_path(settings)
        data = read_json(settings, {})
        hooks = data.get("hooks", {})
        groups = hooks.get("SessionStart", [])
        if record["hook"] in groups:
            hooks["SessionStart"] = [group for group in groups if group != record["hook"]]
            if not hooks["SessionStart"]:
                del hooks["SessionStart"]
            if not hooks:
                data.pop("hooks", None)
            if not data and record.get("settings_created"):
                settings.unlink(missing_ok=True)
            else:
                write_asset(settings, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            removed.append("SessionStart prewarm hook")
        else:
            kept.append("modified or absent SessionStart hook")
        remaining.pop("hook", None)
        remaining.pop("settings", None)
    if remaining["assets"]:
        owned[identifier] = remaining
    else:
        owned.pop(identifier, None)
    write_json(paths()[0] / "integrations.json", owned)
    return {"status": "ok", "removed": removed, "kept": kept}


def integration_status():
    result = []
    for record in manifest().values():
        root = Path(record["root"])
        present = all((root / relative).is_file() for relative in record.get("assets", {}))
        result.append({"client": record["client"], "root": str(root),
                       "state": "configured_unverified" if present else "incomplete",
                       "live_verified": False})
    return result
