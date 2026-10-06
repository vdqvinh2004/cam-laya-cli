"""Describe a pilot without treating forced adoption or subscription tokens as billed savings."""
import json
import statistics
import sys
from pathlib import Path


def estimate(usage):
    # Illustrative public API rates, USD per million; subscription charges are unknown.
    return ((usage["input_tokens"] - usage["cached_input_tokens"]) * 0.1
            + usage["cached_input_tokens"] * 0.01 + usage["output_tokens"] * 0.5) / 1_000_000


def summarize(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    records = [json.loads(line) for line in (directory / "runs.jsonl").read_text().splitlines()]
    rows = []
    pairs = []
    for task in manifest["tasks"]:
        matched = {row["profile"]: row for row in records if row["task"] == task["id"]}
        baseline, candidate = matched.get("baseline"), matched.get("laya")
        if baseline and candidate:
            time_change = 100 * (candidate["elapsed_s"] / baseline["elapsed_s"] - 1)
            estimated_change = 100 * (estimate(candidate["usage"]) / estimate(baseline["usage"]) - 1)
            accepted = candidate.get("worker_counts_delta", {}).get("ok", 0)
            pair = {"task": task["id"], "forced": task["forced_control"],
                    "time_change_percent": time_change, "illustrative_api_cost_change_percent": estimated_change,
                    "laya_decisions": candidate.get("worker_counts_delta", {}).get("requests", 0),
                    "model_inference_calls": candidate.get("worker_counts_delta", {}).get("inference_calls", 0),
                    "accepted_laya_decisions": accepted,
                    "baseline_pass": all(baseline[key] for key in
                                         ("acceptance_pass", "regression_pass", "scope_pass")),
                    "candidate_pass": all(candidate[key] for key in
                                          ("acceptance_pass", "regression_pass", "scope_pass"))}
            pairs.append(pair)
            rows.append(f"| {task['id']} | {'forced' if task['forced_control'] else 'optional'} | "
                        f"{baseline['elapsed_s']:.2f} | {candidate['elapsed_s']:.2f} | {time_change:+.1f}% | "
                        f"{estimated_change:+.1f}% | {pair['laya_decisions']} / {accepted} | "
                        f"{pair['baseline_pass']} / {pair['candidate_pass']} |")
        else:
            rows.append(f"| {task['id']} | {'forced' if task['forced_control'] else 'optional'} | "
                        f"{baseline['elapsed_s'] if baseline else '—'} | "
                        f"{candidate['elapsed_s'] if candidate else '—'} | — | — | — | incomplete |")
    optional = [pair for pair in pairs if not pair["forced"]]
    adopted = sum(pair["laya_decisions"] > 0 for pair in optional)
    optional_candidates = [row for row in records if row["profile"] == "laya" and not row["forced_control"]]
    passed = sum(all(row[key] for key in ("acceptance_pass", "regression_pass", "scope_pass"))
                 for row in records)
    summary = {"runs": len(records), "completed_pairs": len(pairs), "passes": passed,
               "optional_pairs": len(optional), "optional_pairs_using_laya": adopted,
               "optional_candidate_runs": len(optional_candidates),
               "optional_candidate_runs_using_laya": sum(
                   row.get("worker_counts_delta", {}).get("requests", 0) > 0 for row in optional_candidates),
               "total_usage": {key: sum(row["usage"][key] for row in records) for key in records[0]["usage"]},
               "illustrative_api_equivalent_usd": sum(estimate(row["usage"]) for row in records),
               "billed_usd": None, "pairs": pairs,
               "optional_pairs_with_model_inference": sum(pair["model_inference_calls"] > 0 for pair in optional),
               "useful_work_replacement_demonstrated": False, "main_study_started": False,
               "claims": {"speed_saving": False, "billed_saving": False}}
    attempts = []
    for name in ("codex-luna-pilot", "codex-luna-pilot-v2"):
        previous = directory.parent / name / "runs.jsonl"
        if previous.exists():
            attempts.extend(json.loads(line) for line in previous.read_text().splitlines())
    summary["excluded_completed_attempts"] = len(attempts)
    summary["all_recorded_attempts_api_equivalent_usd"] = sum(
        estimate(row["usage"]) for row in records + attempts)
    if optional:
        summary["optional_median_paired_time_change_percent"] = statistics.median(
            pair["time_change_percent"] for pair in optional)
        summary["optional_median_paired_api_equivalent_change_percent"] = statistics.median(
            pair["illustrative_api_cost_change_percent"] for pair in optional)
    stop_path = directory / "stop.json"
    if stop_path.exists():
        summary["stop"] = json.loads(stop_path.read_text())
        stop_note = (f"The pilot stopped after {summary['stop']['observed']:,} uncached input tokens,\n"
                     "at the frozen 150,000 completed-run stop checked between runs. This permits the last run to\n"
                     "cross the stop threshold; it is not a per-request or dollar cap. "
                     f"[Stop record]({directory.name}/stop.json).")
    else:
        stop_note = "All frozen runs completed." if len(records) == manifest["max_runs"] \
            else "Pilot is incomplete; no stop reason was recorded."
    (directory / "analysis.json").write_text(json.dumps(summary, indent=2) + "\n")
    report = f"""# Codex GPT-6 Luna adoption pilot

No useful work replacement or efficiency gain was demonstrated. Luna used CAM Laya only when
forced; {summary['optional_candidate_runs_using_laya']}/{len(optional_candidates)} optional candidate runs used it.
All {passed}/{len(records)} recorded version 3 runs passed independent acceptance, regression, and patch scope.
Only {len(pairs)} pairs completed; the remaining tasks were not used to infer results.
{stop_note}

Exploratory maintenance tasks on one frozen real repository, authored for this pilot.
Not the historical synthetic fixtures, not held-out tasks, and not a paid efficacy study.
Model: `gpt-6-luna`, medium reasoning, default service tier; client `{manifest['client_version']}`.
Matched settings, isolated source copies, alternating baseline/candidate order, one attempt per profile.
Source/acceptance hashes and stop rules: [frozen manifest]({directory.name}/manifest.json).
Raw outcomes: [run records]({directory.name}/runs.jsonl); [analysis]({directory.name}/analysis.json).

{len(records)} runs; {len(pairs)} complete pairs; {passed}/{len(records)} passed independent acceptance,
full regression suite, and patch scope. Optional adoption: {adopted}/{len(optional)} complete optional pairs.
Forced calls are execution controls, excluded from voluntary-adoption and efficacy interpretation.
In the forced pair, Luna said the advice did not change its implementation approach.
Optional pairs with no local decisions measure profile overhead and ordinary run variability;
their numerical differences do not establish an effect of Laya model inference.

| Task | Mode | Baseline seconds | Laya seconds | Time delta | API-equivalent delta | Decisions / accepted | Checks baseline / Laya |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
{chr(10).join(rows)}

Token usage is from Codex `turn.completed` events. Input counts aggregate model requests,
including repeatedly cached context. They are not unique prompt lengths or subscription charges.
Actual billed USD and subscription credit cost remain unknown. An illustrative API-equivalent total
is ${summary['illustrative_api_equivalent_usd']:.4f}, using public Luna input/cached-input/output rates
of $0.10/$0.01/$0.50 per million tokens, checked 2026-10-06. Cache writes and unreported billing
adjustments are excluded. This is not money spent or saved. [Official GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna).
Including {len(attempts)} excluded completed infrastructure attempts, the same illustrative total
is ${summary['all_recorded_attempts_api_equivalent_usd']:.4f}. Interrupted attempts without a final
usage event have unknown usage and are excluded from this total, not counted as zero.

Whole-task timing includes Codex startup, tool calls, task repairs, and agent-run tests.
Independent grader tests run afterward and are excluded from task time identically in both profiles.
The local model was externally warm in all runs. No prewarm-on/off or cold-start comparison was made.
Worker request/accepted counters verify local decisions; each candidate also logs wrapper calls.
Patches remain in isolated workspaces; no trial patch was applied to production source.

An initial infrastructure attempt is retained in [first attempt](codex-luna-pilot/runs.jsonl).
Its agent shell selected system Python and local worker tests failed under restricted networking;
its grader used an incompatible stdout mock and treated Ruff cache files as patch changes.
Corrected acceptance passed that completed patch, but its timing stays excluded.
Version 2 pins an absolute interpreter, permits local socket networking equally in both profiles,
fixes the grader, ignores generated Ruff caches, and gives the candidate skill an absolute CLI path.
Its wrapper then hit a sandbox denial writing the trial log outside the workspace. Those four
completed runs and one interrupted run are retained in [version 2](codex-luna-pilot-v2/runs/).
Version 3 grants each run access to its artifact directory identically in both profiles.
The executable-path hint was the sole skill guidance adjustment; the remaining fixes were harness
repairs. No guidance was retuned from optional-adoption results.
The requested host-skill-discovery flag still left host skills visible in a local prompt preview;
host skill overhead must therefore be treated as shared, not assumed eliminated.

This small single-repository pilot supplies no confidence interval or efficiency claim.
The paid main study remains unlaunched. Its two-repository frozen manifest, budget approval,
enforceable spending cap, repeated pairs, and quality gates still apply: [protocol](evaluation.md).
"""
    (directory.parent / "codex-luna-pilot-results.md").write_text(report)
    print(json.dumps({key: value for key, value in summary.items() if key != "pairs"}, indent=2))


if __name__ == "__main__":
    assert abs(estimate({"input_tokens": 1_000_000, "cached_input_tokens": 500_000,
                         "output_tokens": 100_000}) - 0.105) < 1e-12
    summarize(Path(sys.argv[1]))
