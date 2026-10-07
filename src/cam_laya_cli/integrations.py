"""Project-scoped owned skills. No hooks, no prewarming, no advice injection."""

import hashlib
import json
from importlib.resources import files
from pathlib import Path

from .config import paths, read_json, write_json

SKILLS = {"codex": ".agents/skills/cam-laya/SKILL.md",
          "claude": ".claude/skills/cam-laya/SKILL.md",
          "opencode": ".opencode/skills/cam-laya/SKILL.md"}
# Removed in 0.2.0; uninstalled when found in legacy records. Never recreated.
LEGACY_SETTINGS = {"codex": ".codex/hooks.json", "claude": ".claude/settings.json"}
LEGACY_PLUGIN = ".opencode/plugins/cam-laya-prewarm.js"


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


def install(client, root):
    root = root.resolve()
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")
    owned = manifest()
    identifier = key(client, root)
    previous = owned.get(identifier, {})
    relative = SKILLS[client]
    text = files("cam_laya_cli").joinpath("assets/SKILL.md").read_text()
    path = root / relative
    check_path(path)
    check_path(path.with_name(path.name + ".cam-laya.tmp"))
    if path.exists() and digest(path.read_text()) != previous.get("assets", {}).get(relative):
        raise ValueError(f"unowned or modified integration asset: {relative}")
    write_asset(path, text)
    record = {**previous, "client": client, "root": str(root),
              "assets": {**previous.get("assets", {}), relative: digest(text)}}
    owned[identifier] = record
    write_json(paths()[0] / "integrations.json", owned)
    return {"status": "ok", "client": client, "root": str(root),
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
    plugin = root / LEGACY_PLUGIN
    if client == "opencode" and plugin.exists():
        check_path(plugin)
        plugin.unlink()
        remaining["assets"].pop(LEGACY_PLUGIN, None)
        removed.append(LEGACY_PLUGIN)
    hook = record.get("hook")
    settings_rel = record.get("settings")
    if hook and settings_rel:
        settings = root / settings_rel
        check_path(settings)
        data = read_json(settings, {})
        hooks = data.get("hooks", {})
        groups = hooks.get("SessionStart", [])
        if hook in groups:
            hooks["SessionStart"] = [group for group in groups if group != hook]
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
