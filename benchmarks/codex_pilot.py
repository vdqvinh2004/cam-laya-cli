"""Freeze and run a bounded subscription-authenticated Codex/Laya adoption pilot.

python benchmarks/codex_pilot.py prepare OUTPUT
python benchmarks/codex_pilot.py run OUTPUT
No API-priced or billed-saving claims; no automatic main-study launch.
"""
import hashlib
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
COMMON = """
Make the smallest working change and add a regression check in tests/test_cli.py.
Only modify src/cam_laya_cli/*.py and tests/test_cli.py. Do not modify other files,
install packages, download models, use the network, delegate, or change Git history.
Run PYTHONPATH=src {python} -m unittest discover -s tests -v, then report changes and test result.
Use that absolute Python interpreter for Python commands; login shells reset PATH.
"""
FORCED = """
Pilot execution control: before editing, use the cam-laya skill to make one custom
typed choice with local CAM Laya that classifies this task as input validation,
transport, diagnostics, or another concern. Inspect response and answer status;
treat an accepted value as advice, abstention/unavailable as a reason to resolve
it yourself. State whether the result changed your approach. Then complete task.
"""


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def limits():
    process = subprocess.Popen(["codex", "--no-daemon", "app-server", "--stdio"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    def call(identifier, method, params):
        process.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if selector.select(0.5):
                line = process.stdout.readline()
                if not line:
                    break
                result = json.loads(line)
                if result.get("id") == identifier:
                    if "error" in result:
                        raise RuntimeError(result["error"])
                    return result["result"]
        raise RuntimeError("account limits unavailable")

    try:
        call(1, "initialize", {"clientInfo": {"name": "cam-laya-pilot", "version": "0.1.0"}})
        result = call(2, "account/rateLimits/read", {})
        return {"ordinary_usage_allowed": result.get("ordinaryUsageAllowed"),
                "limits": result["rateLimits"]}
    finally:
        selector.close()
        process.terminate()
        process.wait(timeout=5)


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    tasks = json.loads((ROOT / "benchmarks/codex_pilot_tasks.json").read_text())
    inputs = []
    for directory in ("src", "tests"):
        inputs.extend(path for path in (ROOT / directory).rglob("*")
                      if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    inputs.extend(ROOT / name for name in ("README.md", "pyproject.toml",
                  "benchmarks/guard_cases.json", "benchmarks/decision_cases.json"))
    hashes = {}
    with zipfile.ZipFile(output / "source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(inputs):
            relative = str(path.relative_to(ROOT))
            value = path.read_bytes()
            hashes[relative] = hashlib.sha256(value).hexdigest()
            archive.writestr(relative, value)
    shutil.copyfile(ROOT / "benchmarks/codex_pilot_checks.py", output / "checks.py")
    manifest = {"study": "exploratory adoption pilot; not held-out efficacy study",
                "model": "gpt-6-luna", "reasoning_effort": "medium", "service_tier": "default",
                "auth": "chatgpt", "sandbox": "workspace-write", "prewarm": "externally warm",
                "max_runs": 12, "run_timeout_seconds": 180,
                "completed_run_uncached_input_token_stop": 150000, "completed_run_output_token_stop": 20000,
                "primary_quota_stop_percent": 25, "secondary_quota_stop_percent": 60,
                "spending": "no API auth; no credit purchases; stop well before included quota exhaustion",
                "billed_usd": None, "source_hashes": hashes,
                "checks_sha256": hashlib.sha256((output / "checks.py").read_bytes()).hexdigest(),
                "common_prompt": COMMON.format(python=PYTHON), "forced_control_suffix": FORCED, "tasks": tasks,
                "network_access": "enabled identically for local worker sockets; prompts forbid internet use",
                "host_skill_discovery": "skip flag requested, but local preview still exposes host skills",
                "artifact_write_access": "run directory writable for wrapper logs in both profiles",
                "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "stop_rules": ["Stop on infrastructure/auth/model/usage-record failure or quota threshold.",
                               "Stop main-study progression if any quality failure or absent optional adoption.",
                               "No retries, guidance retuning, or main-study launch in this pilot."],
                "analysis": "Separate forced and optional pairs; report all failures, time, tokens, calls, checks.",
                "client_version": subprocess.check_output(["codex", "--version"], text=True).strip()}
    write_json(output / "manifest.json", manifest)
    (output / "manifest.sha256").write_text(
        hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest() + "\n")
    print(json.dumps({"prepared": str(output), "tasks": len(tasks), "max_runs": 12}), flush=True)


def run(output):
    assert hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest() == \
        (output / "manifest.sha256").read_text().strip(), "manifest changed"
    manifest = json.loads((output / "manifest.json").read_text())
    assert hashlib.sha256((output / "checks.py").read_bytes()).hexdigest() == manifest["checks_sha256"]
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == manifest["runner_sha256"]
    assert not (output / "runs.jsonl").exists(), "pilot already started; never silently rerun"
    auth = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, check=True)
    assert "Logged in using ChatGPT" in auth.stdout + auth.stderr
    runtime = Path("/tmp/cam-laya-pilot-runtime-path").read_text().strip()
    env = os.environ.copy()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        env.pop(key, None)
    env.update(XDG_CONFIG_HOME=runtime + "/config", XDG_STATE_HOME=runtime + "/state",
               PYTHONDONTWRITEBYTECODE="1")
    original = dict(env, PYTHONPATH=str(ROOT / "src"))
    warm = subprocess.run([str(PYTHON), "-I", "-m", "cam_laya_cli", "warm"], env=original,
                          capture_output=True, text=True, timeout=30, check=True)
    write_json(output / "runtime.json", json.loads(warm.stdout))
    def stats():
        child = subprocess.run([str(PYTHON), "-I", "-m", "cam_laya_cli", "stats"], env=original,
                               capture_output=True, text=True, timeout=5, check=True)
        return json.loads(child.stdout)["counts"]

    records = []
    for index, task in enumerate(manifest["tasks"]):
        profiles = ("baseline", "laya") if index % 2 == 0 else ("laya", "baseline")
        for profile in profiles:
            quota = limits()
            current = quota["limits"]
            assert quota["ordinary_usage_allowed"], "ordinary usage disallowed"
            assert current["primary"]["usedPercent"] < manifest["primary_quota_stop_percent"]
            assert current["secondary"]["usedPercent"] < manifest["secondary_quota_stop_percent"]
            assert not current["credits"]["hasCredits"], "paid credits present; pilot stopped"
            if sum(row["usage"]["input_tokens"] - row["usage"]["cached_input_tokens"]
                   for row in records) >= manifest["completed_run_uncached_input_token_stop"] or \
                    sum(row["usage"]["output_tokens"] for row in records) >= 20000:
                raise RuntimeError("completed-run token stop reached")
            destination = output / "runs" / task["id"] / profile
            workspace = destination / "workspace"
            workspace.mkdir(parents=True)
            with zipfile.ZipFile(output / "source.zip") as archive:
                archive.extractall(workspace)
            assert all(hashlib.sha256((workspace / name).read_bytes()).hexdigest() == value
                       for name, value in manifest["source_hashes"].items()), "source changed"
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            local_env = dict(env, PYTHONPATH=str(workspace / "src"))
            tools = destination / "bin"
            tools.mkdir()
            (tools / "python3").symlink_to(PYTHON)
            local_env["PATH"] = str(tools) + os.pathsep + env["PATH"]
            if profile == "laya":
                skill = workspace / ".agents/skills/cam-laya/SKILL.md"
                skill.parent.mkdir(parents=True)
                wrapper = tools / "cam-laya-cli"
                text = (workspace / "src/cam_laya_cli/assets/SKILL.md").read_text()
                marker = text.index("\n---", 4) + len("\n---")
                skill.write_text(text[:marker] + f"\n\nPilot executable: `{wrapper}`. Use this absolute path\n"
                                 "where this skill says `cam-laya-cli`; login shells reset PATH.\n" + text[marker:])
                wrapper.write_text(f'''#!{PYTHON}
import json, os, subprocess, sys, time
started = time.monotonic()
p = subprocess.run([{str(PYTHON)!r}, "-I", "-m", "cam_laya_cli", *sys.argv[1:]],
                   input=sys.stdin.buffer.read() if "--input" in sys.argv and sys.argv[-1] == "-" else None,
                   capture_output=True, env=os.environ)
try: response = json.loads(p.stdout)
except ValueError: response = None
with open({str(destination / "laya-calls.jsonl")!r}, "a") as f:
 f.write(json.dumps({{"args":sys.argv[1:], "exit":p.returncode,
                     "elapsed_s":time.monotonic()-started,"response":response}})+"\\n")
sys.stdout.buffer.write(p.stdout); sys.stderr.buffer.write(p.stderr); sys.exit(p.returncode)
''')
                wrapper.chmod(0o755)
            prompt = task["prompt"] + manifest["common_prompt"]
            if profile == "baseline":
                prompt += "\nUse Codex built-in tools; do not use CAM Laya assistance.\n"
            elif task["forced_control"]:
                prompt += manifest["forced_control_suffix"]
            (destination / "prompt.txt").write_text(prompt)
            command = ["codex", "--no-daemon", "-a", "never", "exec", "--ignore-user-config",
                       "--ephemeral", "--json", "-m", "gpt-6-luna", "-s", "workspace-write",
                       "--disable", "hooks", "--disable", "multi_agent", "--disable", "apps",
                       "--disable", "plugins", "-c", 'forced_login_method="chatgpt"',
                       "--enable", "skip_host_skill_discovery",
                       "-c", "sandbox_workspace_write.network_access=true",
                       "--add-dir", str(destination),
                       "-c", 'model_reasoning_effort="medium"', "-c", 'service_tier="default"',
                       "-C", str(workspace), "-"]
            write_json(destination / "invocation.json", {"command": command, "quota_before": quota})
            counts_before = stats()
            print(json.dumps({"started": task["id"], "profile": profile}), flush=True)
            started = time.monotonic()
            with (destination / "events.jsonl").open("w") as stdout, \
                    (destination / "stderr.txt").open("w") as stderr:
                process = subprocess.Popen(command, env=local_env, stdin=subprocess.PIPE,
                                           stdout=stdout, stderr=stderr, text=True, start_new_session=True)
                try:
                    process.communicate(prompt, timeout=manifest["run_timeout_seconds"])
                    timed_out = False
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGTERM)
                    process.communicate(timeout=10)
            elapsed = time.monotonic() - started
            counts_after = stats()
            events = [json.loads(line) for line in (destination / "events.jsonl").read_text().splitlines()]
            turns = [event["usage"] for event in events if event.get("type") == "turn.completed"]
            usage = {key: sum(turn.get(key, 0) for turn in turns)
                     for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")}
            # No baseline commit needed: compare every file with the frozen snapshot.
            changed = [name for name, digest in manifest["source_hashes"].items()
                       if not (workspace / name).is_file() or
                       hashlib.sha256((workspace / name).read_bytes()).hexdigest() != digest]
            added = [str(path.relative_to(workspace)) for path in workspace.rglob("*")
                     if path.is_file() and ".git" not in path.parts and ".agents" not in path.parts
                     and ".ruff_cache" not in path.parts
                     and "__pycache__" not in path.parts and
                     str(path.relative_to(workspace)) not in manifest["source_hashes"]]
            scope_ok = not added and all(name == "tests/test_cli.py" or
                       (name.startswith("src/cam_laya_cli/") and name.count("/") == 2 and name.endswith(".py"))
                       for name in changed)
            check = subprocess.run([str(PYTHON), str(output / "checks.py"), task["id"]], cwd=workspace,
                                   env=local_env, capture_output=True, text=True, timeout=30)
            regression = subprocess.run([str(PYTHON), "-m", "unittest", "discover", "-s", "tests", "-v"],
                                        cwd=workspace, env=local_env, capture_output=True, text=True, timeout=60)
            (destination / "acceptance.txt").write_text(check.stdout + check.stderr)
            (destination / "regression.txt").write_text(regression.stdout + regression.stderr)
            calls_path = destination / "laya-calls.jsonl"
            calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
            record = {"task": task["id"], "profile": profile, "forced_control": task["forced_control"],
                      "kind": task["kind"], "order": len(records), "elapsed_s": round(elapsed, 3),
                      "exit": process.returncode, "timed_out": timed_out, "usage": usage,
                      "usage_available": bool(turns), "acceptance_pass": check.returncode == 0,
                      "regression_pass": regression.returncode == 0, "scope_pass": scope_ok,
                      "changed": changed, "added": added, "laya_calls": calls, "billed_usd": None}
            record["worker_counts_delta"] = {key: counts_after.get(key, 0) - counts_before.get(key, 0)
                                              for key in counts_after.keys() | counts_before.keys()}
            records.append(record)
            with (output / "runs.jsonl").open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            print(json.dumps({key: record[key] for key in ("task", "profile", "elapsed_s", "usage",
                              "acceptance_pass", "regression_pass", "scope_pass")}), flush=True)
            if process.returncode or timed_out or not turns:
                raise RuntimeError("infrastructure or usage failure; inspect retained run")
    write_json(output / "summary.json", {"runs": len(records), "records": records, "main_study_started": False})


if __name__ == "__main__":
    action, target = sys.argv[1:]
    {"prepare": prepare, "run": run}[action](Path(target).resolve())
