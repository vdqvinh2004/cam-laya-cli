# Evaluation protocol

Frozen 2026-10-06. This protocol separates local interface correctness, model value, transport, and live agent efficacy. No paid run is authorized by this file.

## Local gates

1. Pass unit/integration checks, the 299-case inherited guard corpus, and all 12 inherited deterministic choices.
2. Confirm parallel startup produces one worker, repeated CLI processes reuse weights, socket ownership is enforced, model absence stays distinguishable from abstention, and diagnostics never start a worker.
3. Measure 100 warm short decisions. Target fresh CLI non-engine p95 <=50 ms and complete fresh CLI p95 <=250 ms. Include first call, model load, inference, queue, worker RSS, and all samples. These targets apply only to the reference Mac and short fixture.
4. Compare benchmark-only MCP and persistent IPC over identical requests to the same worker. Counterbalance invocation order; verify output parity. Report initialization independently. This local comparison does not measure model-visible context or live adoption.
5. Run the frozen decision corpus with `benchmarks/evaluate.py --model`. Its SHA-256 is `benchmarks/corpus.sha256`. Development has 60 examples; held-out has 120; source groups are disjoint. Each source has paired option-order/framing variants. Workloads: task routing, error triage, and excerpt relevance.

The corpus is **hand-authored synthetic**, not a public production dataset or a live coding benchmark. It characterizes regressions and selective accuracy on these fixtures only. Reference labels were written before model outputs. The evaluator compares simple rules, model, and rules with model fallback. Development thresholds are selected from 0.5/0.7/0.8/0.9/0.95, maximizing coverage at >=95% observed accepted accuracy, breaking ties toward stricter thresholds. No qualifying threshold means no proposed automatic gate. Held-out results never retune the threshold.

Report predictions, accepted accuracy, coverage, fallback counts, order sensitivity, and latency. Small synthetic samples cannot establish calibrated confidence or deployment accuracy. Passing them does not enable automatic advice hooks.

`--robustness` adds 12 separate negation, positive-control, and paraphrase diagnostics. These were authored after the first screen and are explicitly excluded from its frozen held-out corpus and threshold selection. Keep that chronology visible; they do not establish fresh held-out deployment performance.

## Paid study proposal, awaiting budget approval

Use six separate adoption pilot tasks, then freeze 12 held-out tasks from at least two pinned repositories. Eight require discovery or a genuinely useful bounded classification; four are explicit-target/simple bypass tasks. Every task requires an independent executable check and allowed patch scope. The existing coding fixtures are historical examples only; do not rebrand them as untouched held-out tasks.

Run four matched, counterbalanced baseline/CLI pairs per held-out task, per installed and authenticated client: 48 pairs / 96 runs. Use identical model, reasoning effort, permissions, safety guard profile, repository state, and cache conditions. Baseline omits CAM skill/hook; candidate adds the skill and separately measures prewarm-on/off. Start with one client to fit the approved budget. Claude remains unverified until installed and exercised.

Pilot forced calls demonstrate execution and result handling; unforced prompts test adoption. Allow one pilot-only guidance adjustment. Stop the paid main study if pilot adoption is absent, result handling is incorrect, quality falls, or local model coverage fails to replace useful work. Never force calls in a study presented as voluntary adoption.

Capture client version, model settings, task/repetition/order, independent check, patch-scope result, elapsed time, first useful response, CLI/tool calls, retries, model cold load, and provider input/cached-input/output usage. Record all failures; report infrastructure exclusions under a frozen rule. Freeze the task manifest, fixtures, package commit, and analysis before main runs.

Calculate paired task-level changes and bootstrap 95% intervals by task cluster. A claim of efficiency requires >=10% median improvement in elapsed time and provider-priced token cost, each interval wholly below zero, with candidate check-pass count no lower than baseline and both >=95%. Bypass median regressions must remain <=5%. Include extra calls, fallbacks, discovery, and repairs; count the complete task.

Use published prices dated at evaluation only for explicitly labeled estimates. Actual billed savings need attributable charge records; subscription tokens are not a bill. Tool-schema wire bytes and local Laya token counts are not provider usage.

Before any paid run, present the frozen manifest, client/model, run count, usage estimate, and a hard spending cap for approval. If billing cannot enforce the cap, do not launch the study. Functional CLI delivery remains useful even if efficacy fails; report negative results.
