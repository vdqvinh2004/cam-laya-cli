"""Freeze and evaluate evidence filtering on actual project documents and logs.

python benchmarks/offload_screen.py prepare OUTPUT
python benchmarks/offload_screen.py run OUTPUT
No Codex inference is launched by this local screen.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
DOCS = ["README.md", "docs/local-results.md", "docs/evaluation.md", "src/cam_laya_cli/assets/SKILL.md"]
LOGS = ["docs/codex-luna-pilot/runs/warm_timeout/baseline/events.jsonl",
        "docs/codex-luna-pilot-v2/runs/warm_timeout/laya/events.jsonl"]
STOP_WORDS = set("a an and are as at be before by can did do does for from has how i in is it its "
                 "of on or that the their them these they this to was were what when where which why "
                 "with without would report explain identify find give describe happened caused cause "
                 "cam laya cli codex agent agents project local document log logs excerpt excerpts".split())
CASES = [
    {"id": "negative_infinity", "kind": "log",
     "query": "Why did the warm timeout regression fail for negative infinity? Identify the argument and exact parser error.",
     "evidence": [{"source": LOGS[0], "event": 29,
                   "needle": "('-inf', b'usage: cam-laya-cli warm", "reason": "offending input"},
                  {"source": LOGS[0], "event": 29,
                   "needle": "cam-laya-cli warm: error: argument --timeout: expected one argument",
                   "reason": "parser failure"}]},
    {"id": "permission_boundary", "kind": "log",
     "query": "Why could the CAM executable not complete its status call? Identify the exception and affected log artifact.",
     "evidence": [{"source": LOGS[1], "event": 7,
                   "needle": "PermissionError: [Errno 1] Operation not permitted:", "reason": "permission exception"},
                  {"source": LOGS[1], "event": 7,
                   "needle": "with open('/Volumes/LexarPlaySSD/Develop/Codes/CAM/cam-laya-cli/docs/codex-luna-pilot-v2/runs/warm_timeout/laya/laya-calls.jsonl', \"a\") as f:",
                   "reason": "artifact opened for writing"}]},
    {"id": "worker_unavailable", "kind": "log",
     "query": "Which two unittest cases ended with worker unavailability in the last failing full suite, and what exact exception was reported?",
     "evidence": [{"source": LOGS[0], "event": 33,
                   "needle": "ERROR: test_real_process_reuse_batch_and_parallel_start", "reason": "first affected test"},
                  {"source": LOGS[0], "event": 33,
                   "needle": "ERROR: test_socket_permissions_and_large_record_recovery", "reason": "second affected test"},
                  {"source": LOGS[0], "event": 33,
                   "needle": "cam_laya_cli.engine.Unavailable: worker_not_running", "reason": "exception"}]},
    {"id": "empty_stdout", "kind": "log",
     "query": "Why did the new warm timeout test error while decoding its subprocess output? Identify the assertion location and JSON exception.",
     "evidence": [{"source": LOGS[1], "event": 17,
                   "needle": "ERROR: test_warm_timeout_validation_and_forwarding", "reason": "affected test"},
                  {"source": LOGS[1], "event": 17,
                   "needle": "self.assertEqual(json.loads(child.stdout)", "reason": "stdout decoded"},
                  {"source": LOGS[1], "event": 17,
                   "needle": "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
                   "reason": "JSON exception"}]},
    {"id": "uncertain_answer", "kind": "document",
     "query": "Does exit code zero guarantee a usable decision? Explain abstention handling and whether answer confidence measures accuracy.",
     "evidence": [{"source": DOCS[0], "needle": "exit 0 means a valid response, **including abstention**", "reason": "exit semantics"},
                  {"source": DOCS[0], "needle": "Inspect `status` and individual answer statuses before branching", "reason": "branching check"},
                  {"source": DOCS[0], "needle": "neither is measured accuracy", "reason": "confidence limit"},
                  {"source": DOCS[3], "needle": "Abstention or unavailable means the coding agent resolves the decision", "reason": "fallback action"}]},
    {"id": "cache_and_idle", "kind": "document",
     "query": "Are decision results cached? Explain what stays resident, why changing checkpoints may reload, and when the idle worker exits.",
     "evidence": [{"source": DOCS[0], "needle": "caches weights, not decision results", "reason": "cache scope"},
                  {"source": DOCS[0], "needle": "switching checkpoints may reload weights", "reason": "reload condition"},
                  {"source": DOCS[0], "needle": "An idle worker exits after 30 minutes", "reason": "idle lifetime"}]},
    {"id": "platform_and_provisioning", "kind": "document",
     "query": "Which hardware and operating system can run model inference? When are checkpoints downloaded, and what happens if automatic routing selects an unprovisioned checkpoint?",
     "evidence": [{"source": DOCS[0], "needle": "Runtime v1 requires Apple Silicon and macOS 14+", "reason": "platform"},
                  {"source": DOCS[0], "needle": "Model files use the shared Hugging Face cache; routine decisions are offline", "reason": "download versus inference"},
                  {"source": DOCS[0], "needle": "Automatic routing returns unavailable if its selected checkpoint is missing", "reason": "missing checkpoint"},
                  {"source": DOCS[0], "needle": "Install the MLX extra to run custom questions", "reason": "runtime dependency"}]},
    {"id": "prewarm_and_triggers", "kind": "document",
     "query": "Does session prewarming make recommendations automatically? When should the agent invoke the skill, and what should happen to ordinary coding reasoning?",
     "evidence": [{"source": DOCS[0], "needle": "`--prewarm` adds session-start warming only; it injects no advice", "reason": "hook scope"},
                  {"source": DOCS[3], "needle": "Classify bounded text or batch typed choice, score, and yes/no decisions", "reason": "skill trigger"},
                  {"source": DOCS[3], "needle": "Also use when explicitly asked to use CAM Laya", "reason": "explicit trigger"},
                  {"source": DOCS[3], "needle": "Keep ordinary coding reasoning with the coding agent", "reason": "coding behavior"}]}
]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def words(text):
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOP_WORDS


def split(text, limit=700):
    """Keep lossless spans, splitting at paragraph and line boundaries where possible."""
    spans = []
    offset = 0
    for paragraph in text.splitlines(keepends=True):
        for start in range(0, len(paragraph), limit):
            piece = paragraph[start:start + limit]
            if spans and len(spans[-1][2]) + len(piece) <= limit and not spans[-1][2].endswith("\n\n"):
                begin, _, previous = spans[-1]
                spans[-1] = (begin, offset + start + len(piece), previous + piece)
            else:
                spans.append((offset + start, offset + start + len(piece), piece))
        offset += len(paragraph)
    assert "".join(span[2] for span in spans) == text
    return spans


def baseline(chunks, query, context=False):
    terms = words(query)
    selected = {i for i, chunk in enumerate(chunks) if terms & words(chunk["text"])}
    if context:
        selected |= {j for i in list(selected) for j in (i - 1, i + 1)
                     if 0 <= j < len(chunks) and chunks[j]["origin"] == chunks[i]["origin"]}
    return {chunks[i]["id"] for i in selected}


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    chunks = []
    originals = {}
    hashes = {}
    for source in DOCS + LOGS:
        raw = (ROOT / source).read_bytes()
        hashes[source] = digest(raw)
        if source in DOCS:
            contents = [(None, raw.decode())]
        else:
            events = [json.loads(line) for line in raw.decode().splitlines()]
            contents = [(index, event["item"].get("aggregated_output", "")) for index, event in enumerate(events)
                        if event.get("type") == "item.completed" and
                        event.get("item", {}).get("type") == "command_execution"]
        for event, text in contents:
            originals[(source, event)] = text
            origin = source + (f":event{event}" if event is not None else "")
            for index, (start, end, piece) in enumerate(split(text)):
                chunks.append({"id": f"{origin}:chunk{index}", "origin": origin,
                               "source": source, "event": event, "start": start, "end": end, "text": piece})
    cases = []
    for specification in CASES:
        pool = [chunk for chunk in chunks if (chunk["source"] in LOGS) == (specification["kind"] == "log")]
        requirements = []
        for evidence in specification["evidence"]:
            text = originals[(evidence["source"], evidence.get("event"))]
            start = text.index(evidence["needle"])
            end = start + len(evidence["needle"])
            required = [chunk["id"] for chunk in pool if chunk["source"] == evidence["source"] and
                        chunk["event"] == evidence.get("event") and chunk["start"] < end and chunk["end"] > start]
            assert required
            requirements.append({**evidence, "chunks": required})
        cases.append({"id": specification["id"], "kind": specification["kind"],
                      "query": specification["query"], "requirements": requirements,
                      "chunk_ids": [chunk["id"] for chunk in pool]})
    manifest = {"provenance": "Curated real project docs and captured logs; exploratory, not fresh held-out validation.",
                "broad_coding_trials": "paused", "codex_runs_before_gate": 0,
                "source_hashes": hashes, "chunks": chunks, "cases": cases,
                "model": "english", "checkpoint_revision": "20aed815fc6acde75733882e7ec0e3f28aeb9717",
                "min_confidence": 0.9, "uncertain_policy": "keep on abstention, invalid output, or unavailability",
                "baselines": ["unfiltered", "keyword", "keyword_context"],
                "gate": {"required_evidence_recall": 1.0, "minimum_byte_reduction": 0.5,
                         "extra_reduction_over_best_evidence_preserving_baseline": 0.10,
                         "runtime_errors": 0},
                "threshold_tuning": "none; no retries or retuning after outcomes",
                "runner_sha256": digest(Path(__file__).read_bytes())}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "manifest.sha256").write_text(digest((output / "manifest.json").read_bytes()) + "\n")
    print(json.dumps({"prepared": str(output), "cases": len(cases), "unique_chunks": len(chunks),
                      "classifications": sum(len(case["chunk_ids"]) for case in cases)}), flush=True)


def measure(case, chunks, kept):
    original = sum(len(chunk["text"].encode()) for chunk in chunks)
    retained = sum(len(chunk["text"].encode()) for chunk in chunks if chunk["id"] in kept)
    required = {name for requirement in case["requirements"] for name in requirement["chunks"]}
    missing = sorted(required - kept)
    return {"input_bytes": original, "retained_bytes": retained, "byte_reduction": 1 - retained / original,
            "required_chunks": len(required), "retained_required_chunks": len(required & kept),
            "evidence_recall": len(required & kept) / len(required), "missing_chunks": missing,
            "retained_ids": sorted(kept)}


def run(output):
    assert digest((output / "manifest.json").read_bytes()) == (output / "manifest.sha256").read_text().strip()
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["runner_sha256"] == digest(Path(__file__).read_bytes()), "runner changed after freeze"
    assert not (output / "results.json").exists(), "screen already completed; do not silently retune"
    runtime = Path(tempfile.mkdtemp(prefix="cam-offload-screen-"))
    environment = dict(os.environ, XDG_CONFIG_HOME=str(runtime / "config"),
                       XDG_STATE_HOME=str(runtime / "state"), PYTHONDONTWRITEBYTECODE="1")
    # Reuse only the already-provisioned pinned checkpoint; screen never downloads models.
    previous = Path(Path("/tmp/cam-laya-pilot-runtime-path").read_text().strip()) / "config/cam-laya-cli/config.json"
    provisioned = json.loads(previous.read_text())["models"]["english"]
    assert provisioned["revision"] == manifest["checkpoint_revision"]
    configuration = runtime / "config/cam-laya-cli"
    configuration.mkdir(parents=True, mode=0o700)
    (configuration / "config.json").write_text(json.dumps({"models": {"english": provisioned}}))
    command = [str(PYTHON), "-I", "-m", "cam_laya_cli"]
    started = time.perf_counter()
    warm = subprocess.run(command + ["warm"], env=environment, capture_output=True, text=True, timeout=30)
    (output / "warm.json").write_text(warm.stdout)
    warm_seconds = time.perf_counter() - started
    assert warm.returncode == 0, warm.stderr
    indexed = {chunk["id"]: chunk for chunk in manifest["chunks"]}
    outcomes = []
    try:
        for case in manifest["cases"]:
            chunks = [indexed[name] for name in case["chunk_ids"]]
            methods = {}
            for name in manifest["baselines"]:
                started = time.perf_counter()
                kept = {chunk["id"] for chunk in chunks} if name == "unfiltered" \
                    else baseline(chunks, case["query"], context=name == "keyword_context")
                methods[name] = {**measure(case, chunks, kept), "elapsed_ms": (time.perf_counter() - started) * 1000}
            requests = [{"id": str(index), "model": "english", "min_confidence": manifest["min_confidence"],
                         "state": "Information need: " + case["query"] + "\nPassage:\n" + chunk["text"],
                         "questions": {"relevance": {"type": "choice", "instructions":
                         "Keep passages containing facts needed to answer the information need, including qualifications and counterexamples. Discard only unrelated content.",
                         "criteria": {"keep": "Contains evidence relevant to the information need",
                                      "discard": "Unrelated to the information need"}}}} for index, chunk in enumerate(chunks)]
            request_path = output / (case["id"] + "-requests.jsonl")
            request_path.write_text("".join(json.dumps(value) + "\n" for value in requests))
            started = time.perf_counter()
            process = subprocess.run(command + ["batch", "--input", str(request_path), "--timeout", "30"],
                                     env=environment, capture_output=True, text=True, timeout=180)
            elapsed = (time.perf_counter() - started) * 1000
            (output / (case["id"] + "-responses.jsonl")).write_text(process.stdout)
            (output / (case["id"] + "-stderr.txt")).write_text(process.stderr)
            responses = [json.loads(line) for line in process.stdout.splitlines()]
            assert len(responses) == len(chunks), "response count mismatch"
            kept = set()
            errors = abstentions = accepted = 0
            for index, (chunk, response) in enumerate(zip(chunks, responses, strict=True)):
                answer = response.get("answers", {}).get("relevance", {})
                valid = response.get("id") == str(index) and response.get("status") == "ok" \
                    and answer.get("status") == "ok" and answer.get("value") in {"keep", "discard"}
                if valid:
                    accepted += 1
                elif response.get("status") == "abstained":
                    abstentions += 1
                else:
                    errors += 1
                if not valid or answer["value"] == "keep":
                    kept.add(chunk["id"])
            methods["laya"] = {**measure(case, chunks, kept), "elapsed_ms": elapsed, "accepted": accepted,
                               "abstained": abstentions, "errors": errors, "cli_exit": process.returncode}
            outcomes.append({"case": case["id"], "kind": case["kind"], "methods": methods})
            print(json.dumps({"case": case["id"], "laya_recall": methods["laya"]["evidence_recall"],
                              "laya_reduction": methods["laya"]["byte_reduction"],
                              "abstentions": abstentions, "errors": errors}), flush=True)
    finally:
        subprocess.run(command + ["stop"], env=environment, capture_output=True, timeout=10)
    aggregates = {}
    for method in [*manifest["baselines"], "laya"]:
        rows = [row["methods"][method] for row in outcomes]
        aggregates[method] = {"required_chunks": sum(row["required_chunks"] for row in rows),
                              "retained_required_chunks": sum(row["retained_required_chunks"] for row in rows),
                              "complete_cases": sum(not row["missing_chunks"] for row in rows),
                              "input_bytes": sum(row["input_bytes"] for row in rows),
                              "retained_bytes": sum(row["retained_bytes"] for row in rows),
                              "elapsed_ms": sum(row["elapsed_ms"] for row in rows)}
        aggregate = aggregates[method]
        aggregate["evidence_recall"] = aggregate["retained_required_chunks"] / aggregate["required_chunks"]
        aggregate["byte_reduction"] = 1 - aggregate["retained_bytes"] / aggregate["input_bytes"]
    qualifying = [name for name in manifest["baselines"] if aggregates[name]["complete_cases"] == len(outcomes)]
    best = max(qualifying, key=lambda name: aggregates[name]["byte_reduction"])
    laya = aggregates["laya"]
    checks = {"all_required_evidence_preserved": laya["complete_cases"] == len(manifest["cases"]),
              "at_least_half_input_removed": laya["byte_reduction"] >= manifest["gate"]["minimum_byte_reduction"],
              "beats_best_qualifying_baseline": laya["byte_reduction"] - aggregates[best]["byte_reduction"] >=
              manifest["gate"]["extra_reduction_over_best_evidence_preserving_baseline"],
              "no_runtime_errors": all(row["methods"]["laya"]["errors"] == 0 and
                                       row["methods"]["laya"]["cli_exit"] == 0 for row in outcomes)}
    result = {"broad_trials": "paused", "warm_seconds": warm_seconds, "aggregates": aggregates,
              "best_qualifying_baseline": best, "gate_checks": checks, "gate_passed": all(checks.values()),
              "paired_luna_trial": "eligible for bounded pilot" if all(checks.values()) else "skipped: gate failed",
              "input_measure": "UTF-8 bytes, not provider token usage", "provider_tokens": None, "billed_usd": None,
              "outcomes": outcomes}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "outcomes"}, indent=2), flush=True)


if __name__ == "__main__":
    # Small executable check for lossless chunking, contextual search, and missing-evidence detection.
    for text in ("", "a\nb\n", "a" * 1401, "one\n\ntwo\n", "đ" * 701):
        assert "".join(piece for _, _, piece in split(text)) == text
    sample = [{"id": str(i), "origin": "same", "text": value}
              for i, value in enumerate(("noise", "PermissionError", "context"))]
    assert baseline(sample, "permission", context=False) == {"1"}
    assert baseline(sample, "permission", context=True) == {"0", "1", "2"}
    assert measure({"requirements": [{"chunks": ["1", "2"]}]}, sample, {"1"})["missing_chunks"] == ["2"]
    action, destination = sys.argv[1:]
    {"prepare": prepare, "run": run}[action](Path(destination).resolve())
