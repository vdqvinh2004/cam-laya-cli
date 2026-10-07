import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cam_laya_cli.engine import decide, validate
from cam_laya_cli.integrations import install, uninstall
from cam_laya_cli.presets import OPTIONS, hard_risk

ROOT = Path(__file__).resolve().parents[1]


class Decisions(unittest.TestCase):
    def test_legacy_deterministic_choices_without_model(self):
        cases = json.loads((ROOT / "benchmarks/decision_cases.json").read_text())
        self.assertEqual(len(cases), 12)
        for case in cases:
            with self.subTest(case=case["id"]):
                result = decide({"preset": case["policy"], "state": case["state"]})
                self.assertEqual(result["decision"], case["expected"])
                self.assertEqual(result["source"], "rule")
                self.assertEqual(result["status"], "ok")

    def test_guard_corpus(self):
        cases = json.loads((ROOT / "benchmarks/guard_cases.json").read_text())["cases"]
        self.assertEqual(len(cases), 299)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(bool(hard_risk(case["action"])), case["expect"] == "block")

    def test_tool_choice_rule_and_deferral(self):
        result = decide({"preset": "tool_choice",
                         "state": {"current_phase": "coding", "tests_available": False}})
        self.assertEqual(result["decision"], "ask_user")
        self.assertEqual(result["status"], "ok")
        result = decide({"preset": "tool_choice", "state": {"current_phase": "debugging"}})
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["decision"], "defer_to_agent")
        self.assertEqual(result["reason_code"], "no_deterministic_rule")

    def test_unknown_next_action_defers(self):
        result = decide({"preset": "next_action", "state": {}})
        self.assertEqual(result["status"], "abstained")
        self.assertEqual(result["decision"], "defer_to_agent")

    def test_risk_gates(self):
        safe = decide({"preset": "risk_check", "state": {"action": "git status"}})
        self.assertEqual((safe["risk"], safe["requires_human"]), ("safe", False))
        bad = decide({"preset": "risk_check", "state": {"action": "rm -rf / --no-preserve-root"}})
        self.assertEqual((bad["risk"], bad["requires_human"]), ("destructive", True))
        force = decide({"preset": "risk_check", "state": {"action": "git push --force"}})
        self.assertEqual((force["risk"], force["requires_human"]), ("high", True))
        unknown = decide({"preset": "risk_check", "state": {"action": "custom-operation"}})
        self.assertEqual(unknown["status"], "abstained")
        self.assertEqual(unknown["risk"], "unknown")
        self.assertTrue(unknown["requires_human"])

    def test_input_boundaries(self):
        for bad in [{"preset": "nope", "state": {}},
                    {"preset": "risk_check", "state": "text"},
                    {"preset": "risk_check", "state": {"action": 1}},
                    {"preset": "risk_check", "state": {}, "questions": {}},
                    {"preset": "risk_check", "state": {}, "model": "english"},
                    {"preset": "risk_check", "state": {}, "id": "x" * 129},
                    {"state": {}},
                    "text"]:
            with self.assertRaises(ValueError):
                validate(bad)
        result = decide({"id": "abc", "preset": "risk_check", "state": {"action": "git status"}})
        self.assertEqual(result["id"], "abc")

    def test_no_route_task_preset(self):
        self.assertNotIn("route_task", OPTIONS)
        with self.assertRaises(ValueError):
            validate({"preset": "route_task", "state": {}})


class Integration(unittest.TestCase):
    def test_install_uninstall_all_clients(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state"}):
            root = Path(directory).resolve() / "project"
            root.mkdir()
            for client, skill in [("codex", ".agents/skills/cam-laya/SKILL.md"),
                                  ("claude", ".claude/skills/cam-laya/SKILL.md"),
                                  ("opencode", ".opencode/skills/cam-laya/SKILL.md")]:
                result = install(client, root)
                self.assertEqual(result["status"], "ok")
                self.assertTrue((root / skill).is_file())
                removed = uninstall(client, root)
                self.assertIn(skill, removed["removed"])
                self.assertFalse((root / skill).exists())

    def test_unowned_assets_survive(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "XDG_CONFIG_HOME": directory + "/config"}):
            root = Path(directory).resolve() / "project"
            root.mkdir()
            install("codex", root)
            skill = root / ".agents/skills/cam-laya/SKILL.md"
            skill.write_text("user changed this")
            with self.assertRaises(ValueError):
                install("codex", root)
            self.assertIn(".agents/skills/cam-laya/SKILL.md", uninstall("codex", root)["kept"])
            self.assertEqual(skill.read_text(), "user changed this")

    def test_legacy_hook_and_plugin_cleanup(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state"}):
            from cam_laya_cli.config import write_json
            root = Path(directory).resolve() / "project"
            root.mkdir()
            install("codex", root)
            install("opencode", root)
            hook = {"matcher": "startup|resume|clear", "hooks": []}
            plugin = root / ".opencode/plugins/cam-laya-prewarm.js"
            plugin.parent.mkdir(parents=True, exist_ok=True)
            plugin.write_text("// legacy")
            config = Path(directory + "/config/cam-laya-cli/integrations.json")
            owned = json.loads(config.read_text())
            for identifier, record in owned.items():
                if record["client"] == "codex":
                    record["hook"] = hook
                    record["settings"] = ".codex/hooks.json"
                    settings = root / ".codex/hooks.json"
                    settings.parent.mkdir(parents=True, exist_ok=True)
                    settings.write_text(json.dumps({"hooks": {"SessionStart": [hook]}}))
                if record["client"] == "opencode":
                    record["assets"][".opencode/plugins/cam-laya-prewarm.js"] = "legacy"
            write_json(config, owned)
            codex = uninstall("codex", root)
            self.assertIn("SessionStart prewarm hook", codex["removed"])
            self.assertTrue(plugin.exists())
            opencode = uninstall("opencode", root)
            self.assertIn(".opencode/plugins/cam-laya-prewarm.js", opencode["removed"])
            self.assertFalse(plugin.exists())


class WorkerlessCLI(unittest.TestCase):
    def run_cli(self, *args, stdin=None, env=None):
        base = dict(os.environ)
        if env:
            base.update(env)
        return subprocess.run([sys.executable, "-m", "cam_laya_cli", *args],
                              input=stdin, capture_output=True, timeout=30, env=base)

    def test_preset_batch_doctor_status_benchmark(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state"}
            child = self.run_cli("preset", "test_decision", "--input", str(ROOT / "examples/state.json"),
                                 env=env)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(json.loads(child.stdout)["decision"], "debug_failure")
            child = self.run_cli("preset", "test_decision", "--input", "-", stdin=b"nope", env=env)
            self.assertEqual(child.returncode, 2)
            batch = b'{"preset":"risk_check","state":{"action":"git status"}}\n{"bad":1}\n'
            child = self.run_cli("batch", "--input", "-", stdin=batch, env=env)
            self.assertEqual(child.returncode, 2)
            rows = [json.loads(line) for line in child.stdout.splitlines()]
            self.assertEqual([r["status"] for r in rows], ["ok", "error"])
            for command in ("doctor", "status"):
                child = self.run_cli(command, env=env)
                self.assertEqual(child.returncode, 0, child.stderr)
                self.assertEqual(json.loads(child.stdout)["status"], "ok")
            child = self.run_cli("benchmark", "--samples", "5", env=env)
            self.assertEqual(child.returncode, 0, child.stderr)
            result = json.loads(child.stdout)
            self.assertEqual(result["status"], "ok")
            self.assertLess(result["direct"]["p95_ms"], 50)


if __name__ == "__main__":
    unittest.main()
