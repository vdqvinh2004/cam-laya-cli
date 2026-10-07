import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from cam_laya_cli.engine import Engine, Runtime, Unavailable, validate
from cam_laya_cli.integrations import install, uninstall
from cam_laya_cli.presets import OPTIONS, hard_risk
from cam_laya_cli.worker import MAX_BYTES, Client, parse, request

ROOT = Path(__file__).resolve().parents[1]
QUESTION = {"state": "Example", "questions": {
    "q": {"type": "choice", "instructions": "Choose.", "criteria": ["alpha", "beta"]}}}


class FakeAgent:
    def __init__(self, usage=None, confidence=.8):
        self.usage = usage or {"truncated_questions": []}
        self.confidence = confidence

    def predict(self, state, questions):
        answers = {}
        for key, question in questions.items():
            kind = question["type"]
            answers[key] = {"type": kind, "confidence": self.confidence,
                            "answer_confidence": self.confidence,
                            {"choice": "choice", "score": "score", "noul": "noul"}[kind]:
                            list(question["criteria"])[0] if kind == "choice" else .75}
        return {"answers": answers, "usage": self.usage}


class FakeRuntime:
    def __init__(self, agent=None, unavailable=False, uncalibrated=False):
        self.agent = agent or FakeAgent()
        self.unavailable = unavailable
        self.bad_temperature = uncalibrated
        self.calls = 0

    def route(self, *_):
        return "english"

    def load(self, *_):
        if self.unavailable:
            raise Unavailable("checkpoint_not_cached")
        self.calls += 1
        return self.agent

    def uncalibrated(self, *_):
        return self.bad_temperature


class Decisions(unittest.TestCase):
    def test_guard_corpus_and_legacy_choices(self):
        cases = json.loads((ROOT / "benchmarks/guard_cases.json").read_text())["cases"]
        self.assertEqual(len(cases), 299)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(bool(hard_risk(case["action"])), case["expect"] == "block")
        runtime = FakeRuntime(unavailable=True)
        engine = Engine(runtime)
        for case in json.loads((ROOT / "benchmarks/decision_cases.json").read_text()):
            result = engine.decide({"preset": case["policy"], "state": case["state"]})
            self.assertEqual(result["decision"], case["expected"])
            self.assertEqual(result["source"], "rule")
        self.assertEqual(runtime.calls, 0)

    def test_custom_types_and_abstention(self):
        value = copy.deepcopy(QUESTION)
        value["questions"].update({
            "score": {"type": "score", "instructions": "Rate.", "criteria": ["low", "high"]},
            "boolean": {"type": "noul", "instructions": "Is relevant?"}})
        result = Engine(FakeRuntime()).decide(value)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["answers"]["boolean"]["value"], .75)
        self.assertEqual(result["answers"]["q"]["abstention"], "unevaluated")
        value["min_confidence"] = .9
        result = Engine(FakeRuntime()).decide(value)
        self.assertEqual(result["status"], "abstained")
        self.assertIsNone(result["answers"]["q"]["value"])
        self.assertEqual(result["answers"]["q"]["reason_code"], "low_confidence")

    def test_diagnostics_abstain_and_unavailable_never_authorizes(self):
        variants = [(FakeRuntime(FakeAgent({"truncated_questions": ["q"]})), "truncated_state"),
                    (FakeRuntime(FakeAgent({"options": {"q": {}}})), "collapsed_options"),
                    (FakeRuntime(uncalibrated=True), "uncalibrated_temperature")]
        for runtime, reason in variants:
            result = Engine(runtime).decide(QUESTION)
            self.assertEqual(result["answers"]["q"]["reason_code"], reason)
        result = Engine(FakeRuntime(unavailable=True)).decide({
            "preset": "risk_check", "state": {"action": "custom-operation"}})
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["requires_human"])
        result = Engine(FakeRuntime()).decide({"preset": "risk_check", "state": {"action": "custom-operation"}})
        self.assertTrue(result["requires_human"])

    def test_tool_choice_preset(self):
        runtime = FakeRuntime(unavailable=True)
        result = Engine(runtime).decide({
            "preset": "tool_choice", "state": {"current_phase": "coding", "tests_available": False}})
        self.assertEqual(result["decision"], "ask_user")
        self.assertEqual(result["source"], "rule")
        self.assertEqual(runtime.calls, 0)
        runtime = FakeRuntime()
        result = Engine(runtime).decide({
            "preset": "tool_choice",
            "state": {"current_phase": "debugging", "last_test_result": "failed", "changed_files": 2}})
        self.assertEqual(result["status"], "ok")
        self.assertIn(result["decision"], OPTIONS["tool_choice"])
        self.assertTrue(result.get("experimental"))
        result = Engine(FakeRuntime(unavailable=True)).decide({
            "preset": "tool_choice", "state": {"current_phase": "debugging"}})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["decision"], "defer_to_agent")
        with self.assertRaises(ValueError):
            validate({"preset": "tool_choice", "state": "text"})

    def test_input_boundaries(self):
        for raw in [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'x' * (MAX_BYTES + 1)]:
            with self.assertRaises(ValueError):
                parse(raw)
        for field, bad in [("model", []), ("min_confidence", float("nan")), ("state", None)]:
            value = {**QUESTION, field: bad}
            with self.assertRaises(ValueError):
                validate(value)
        value = copy.deepcopy(QUESTION)
        value["questions"]["q"]["criteria"] = ["same", "same"]
        with self.assertRaises(ValueError):
            validate(value)
        self.assertEqual(parse('{"state":"Xin chào"}'.encode())["state"], "Xin chào")

    def test_invalid_model_output_and_temperature_gate(self):
        runtime = FakeRuntime(FakeAgent(confidence=float("nan")))
        self.assertEqual(Engine(runtime).decide(QUESTION)["status"], "unavailable")
        agent = FakeAgent()
        with patch.object(agent, "predict", return_value={"answers": {}, "usage": {}}):
            self.assertEqual(Engine(FakeRuntime(agent)).decide(QUESTION)["status"], "unavailable")
        # Validate the native temperature adapter without requiring MLX in base installs.
        import types

        module = types.ModuleType("laya_mlx.common")
        module.QTYPES = {"choice": 0, "score": 1, "noul": 2}
        module.temp_bucket = lambda kind, count: "choice:11+" if count >= 11 else "choice:2"
        agent = types.SimpleNamespace(temperature_by_options_raw={"choice:11+": .1},
                                      temperature_by_options={"choice:11+": .5},
                                      temperature_raw=[1., 1., 1.], temperature=[1., 1., 1.])
        with patch.dict(sys.modules, {"laya_mlx.common": module}):
            self.assertTrue(Runtime().uncalibrated(agent, "choice", 12))
            self.assertFalse(Runtime().uncalibrated(agent, "choice", 2))


class Integration(unittest.TestCase):
    def test_owned_install_merge_and_uninstall(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state"}):
            root = Path(directory).resolve() / "project"
            root.mkdir()
            settings = root / ".claude/settings.json"
            settings.parent.mkdir()
            original = {"permissions": {"allow": ["Bash(git status)"]},
                        "hooks": {"SessionStart": [{"hooks": [{"command": "existing"}]}]}}
            settings.write_text(json.dumps(original))
            install("claude", root, True)
            install("claude", root, True)
            self.assertEqual(len(json.loads(settings.read_text())["hooks"]["SessionStart"]), 2)
            result = uninstall("claude", root)
            self.assertFalse(result["kept"])
            self.assertEqual(json.loads(settings.read_text()), original)
            self.assertFalse((root / ".claude/skills/cam-laya/SKILL.md").exists())
            for client in ["codex", "opencode"]:
                install(client, root, True)
                self.assertFalse(uninstall(client, root)["kept"])

    def test_unowned_or_modified_assets_survive(self):
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


class Worker(unittest.TestCase):
    def test_real_process_reuse_batch_and_parallel_start(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state"}):
            value = {"op": "decide", "request": {
                "preset": "test_decision", "state": {"last_test_result": "failed"}}}
            try:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(lambda _: request(value), range(8)))
                self.assertTrue(all(x["decision"] == "debug_failure" for x in results))
                before = request({"op": "status"}, start=False)
                with Client() as client:
                    client.call(value)
                    client.call(value)
                after = request({"op": "status"}, start=False)
                self.assertEqual(before["pid"], after["pid"])
                self.assertEqual(after["model_loads"], 0)
                valid = json.dumps(value["request"])
                batch = (valid + '\n{"bad":1}\n' + valid + '\n').encode()
                child = subprocess.run([sys.executable, "-m", "cam_laya_cli", "batch"],
                                       input=batch, capture_output=True, timeout=10)
                self.assertEqual(child.returncode, 2)
                rows = [json.loads(line) for line in child.stdout.splitlines()]
                self.assertEqual([x["status"] for x in rows], ["ok", "error", "ok"])
                snapshot = request({"op": "stats"}, start=False)
                self.assertNotIn("state", json.dumps(snapshot))
            finally:
                request({"op": "stop"}, start=False)
                # Give server finalization time to unlink its socket before temporary cleanup.
                time.sleep(1.1)

    def test_diagnostics_do_not_start_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "XDG_CONFIG_HOME": directory + "/config",
                   "XDG_STATE_HOME": directory + "/state"}
            child = subprocess.run([sys.executable, "-m", "cam_laya_cli", "doctor"],
                                   env=env, capture_output=True, timeout=10)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertFalse(Path(directory + "/state").exists())

    def test_socket_permissions_and_large_record_recovery(self):
        from cam_laya_cli.config import paths

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "XDG_CONFIG_HOME": directory + "/config", "XDG_STATE_HOME": directory + "/state"}):
            value = {"preset": "test_decision", "state": {"last_test_result": "failed"}}
            try:
                request({"op": "decide", "request": value})
                sock = paths()[2] / "worker.sock"
                sock.chmod(0o666)
                with self.assertRaises(PermissionError):
                    request({"op": "status"}, start=False)
                sock.chmod(0o600)
                raw = b'x' * (MAX_BYTES + 100) + b'\n' + json.dumps(value).encode() + b'\n'
                child = subprocess.run([sys.executable, "-m", "cam_laya_cli", "batch"],
                                       input=raw, capture_output=True, timeout=10)
                self.assertEqual([json.loads(row)["status"] for row in child.stdout.splitlines()],
                                 ["error", "ok"])
            finally:
                request({"op": "stop"}, start=False)
                time.sleep(1.1)


if __name__ == "__main__":
    unittest.main()
