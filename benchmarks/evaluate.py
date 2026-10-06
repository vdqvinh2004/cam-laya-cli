"""Offline local rules/model screen. No paid calls or deployment accuracy claims."""

import argparse
import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from cam_laya_cli.presets import deterministic_choice, hard_risk
from cam_laya_cli.worker import Client

ROOT = Path(__file__).resolve().parent


def simple_rule(case):
    state = case["request"]["state"]
    if case["workload"] == "routing":
        for pattern, label in [(r"research|investigate|compare|study|primary documentation", "research"),
                               (r"write.*test|add.*test|extend.*coverage|create tests", "testing"),
                               (r"package|dependency|lockfile|library", "dependency"),
                               (r"readme|documentation|\bdocs\b|usage guide", "documentation"),
                               (r"configur|settings|ci matrix|docker", "configuration")]:
            if re.search(pattern, state, re.I):
                return label
        return None
    if case["workload"] == "triage":
        for pattern, label in [(r"modulenotfound|importerror|dependency|package|compiler", "dependency"),
                               (r"syntaxerror|indentationerror|TS1005", "syntax"),
                               (r"assert|expected.*(?:received|got)|test failed", "assertion"),
                               (r"permission|EACCES|access.*denied|operation not permitted", "permission"),
                               (r"connection|ECONNREFUSED|TLS|timed out|HTTP 503", "network")]:
            if re.search(pattern, state, re.I):
                return label
    return None


def summarize(rows, threshold):
    model_accepted = [row for row in rows if row["value"] is not None and row["confidence"] >= threshold]
    hybrid = [(row["rule"] if row["rule"] is not None else
               row["value"] if row in model_accepted else None, row["expected"]) for row in rows]
    return {"cases": len(rows), "model_accuracy": sum(row["value"] == row["expected"] for row in rows) / len(rows),
            "model_accepted": len(model_accepted), "model_coverage": len(model_accepted) / len(rows),
            "accepted_accuracy": sum(row["value"] == row["expected"] for row in model_accepted)
                / len(model_accepted) if model_accepted else None,
            "rules_accepted": sum(row["rule"] is not None for row in rows),
            "rules_correct": sum(row["rule"] == row["expected"] for row in rows),
            "fallback_cases": len(rows) - len(model_accepted),
            "hybrid_accepted": sum(value is not None for value, _ in hybrid),
            "hybrid_correct": sum(value == expected for value, expected in hybrid),
            "median_latency_ms": sorted(row["latency_ms"] for row in rows)[len(rows) // 2]}


def evaluate(with_model=False, robustness=False):
    guard = json.loads((ROOT / "guard_cases.json").read_text())["cases"]
    decisions = json.loads((ROOT / "decision_cases.json").read_text())
    corpus_path = ROOT / "decision_corpus.json"
    corpus = json.loads(corpus_path.read_text())
    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    if digest != (ROOT / "corpus.sha256").read_text().split()[0]:
        raise ValueError("frozen corpus digest changed")
    groups = defaultdict(set)
    for case in corpus["cases"]:
        groups[case["split"]].add(case["source_group"])
    if groups["development"] & groups["heldout"]:
        raise ValueError("source-group split leakage")
    result = {"guard": {"cases": len(guard), "passed": sum(
        bool(hard_risk(case["action"])) == (case["expect"] == "block") for case in guard)},
        "legacy_rules": {"cases": len(decisions), "passed": sum(
            deterministic_choice(case["policy"], case["state"]) == case["expected"] for case in decisions)},
        "corpus_sha256": digest, "corpus_provenance": corpus["provenance"],
        "development_cases": sum(case["split"] == "development" for case in corpus["cases"]),
        "heldout_cases": sum(case["split"] == "heldout" for case in corpus["cases"]),
        "provider_tokens": None, "billed_usd": None, "model_evaluated": with_model}
    if with_model:
        rows = []
        with Client() as client:
            for case in corpus["cases"]:
                start = time.perf_counter()
                out = client.call({"op": "decide", "request": case["request"]})
                if out["status"] not in {"ok", "abstained"}:
                    raise RuntimeError(f"model unavailable: {out.get('reason_code')}")
                answer = out["answers"]["decision"]
                rows.append({"id": case["id"], "workload": case["workload"], "split": case["split"],
                             "source_group": case["source_group"], "expected": case["expected"],
                             "value": answer["value"], "confidence": answer["answer_confidence"],
                             "rule": simple_rule(case), "status": answer["status"],
                             "latency_ms": round((time.perf_counter() - start) * 1000, 3)})
        report = {}
        for workload in sorted({row["workload"] for row in rows}):
            development = [row for row in rows if row["workload"] == workload and row["split"] == "development"]
            heldout = [row for row in rows if row["workload"] == workload and row["split"] == "heldout"]
            choices = [(threshold, summarize(development, threshold)) for threshold in [.5, .7, .8, .9, .95]]
            eligible = [(threshold, summary) for threshold, summary in choices
                        if summary["accepted_accuracy"] is not None and summary["accepted_accuracy"] >= .95]
            selected = max(eligible, key=lambda x: (x[1]["model_coverage"], x[0])) if eligible else None
            threshold = selected[0] if selected else 1.0
            report[workload] = {"development_threshold_found": bool(selected), "threshold": threshold,
                                "development": summarize(development, threshold),
                                "heldout": summarize(heldout, threshold)}
        variants = defaultdict(list)
        for row in rows:
            variants[row["id"].rsplit("-", 1)[0]].append(row["value"])
        result["paired_variants"] = {"pairs": len(variants), "value_changes": sum(
            len(set(values)) > 1 for values in variants.values())}
        result.update(workloads=report, predictions=rows,
                      threshold_policy="Highest development coverage at >=95% observed accepted accuracy; ties stricter. No eligible threshold means no proposed automatic gate.",
                      deployment_validated=False)
        if robustness:
            diagnostic = json.loads((ROOT / "robustness_cases.json").read_text())
            answers = []
            with Client() as client:
                for case in diagnostic["cases"]:
                    payload = {"state": case["state"], "model": "english", "questions": {
                        "decision": {"type": "choice", "instructions":
                                     "Does the user currently request cancellation of their account or subscription?",
                                     "criteria": {"A": "Cancellation is currently requested",
                                                  "B": "Cancellation is not currently requested"}}}}
                    out = client.call({"op": "decide", "request": payload})
                    answer = out.get("answers", {}).get("decision", {})
                    answers.append({"id": case["id"], "expected": case["expected"],
                                    "value": answer.get("value"),
                                    "confidence": answer.get("answer_confidence"),
                                    "status": out["status"]})
            result["robustness_diagnostics"] = {"provenance": diagnostic["provenance"],
                "cases": len(answers), "correct": sum(row["value"] == row["expected"] for row in answers),
                "predictions": answers}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", action="store_true")
    parser.add_argument("--robustness", action="store_true", help="additional post-screen diagnostics; needs --model")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.robustness and not args.model:
        parser.error("--robustness requires --model")
    result = evaluate(args.model, args.robustness)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(json.dumps({k: v for k, v in result.items() if k != "predictions"}, indent=2))
    if result["guard"]["passed"] != result["guard"]["cases"] or result["legacy_rules"]["passed"] != 12:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
