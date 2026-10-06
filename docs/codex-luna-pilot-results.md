# Codex GPT-6 Luna adoption pilot

No useful work replacement or efficiency gain was demonstrated. Luna used CAM Laya only when
forced; 0/3 optional candidate runs used it.
All 7/7 recorded version 3 runs passed independent acceptance, regression, and patch scope.
Only 3 pairs completed; the remaining tasks were not used to infer results.
The pilot stopped after 157,992 uncached input tokens,
at the frozen 150,000 completed-run stop checked between runs. This permits the last run to
cross the stop threshold; it is not a per-request or dollar cap. [Stop record](codex-luna-pilot-v3/stop.json).

Exploratory maintenance tasks on one frozen real repository, authored for this pilot.
Not the historical synthetic fixtures, not held-out tasks, and not a paid efficacy study.
Model: `gpt-6-luna`, medium reasoning, default service tier; client `codex-cli 0.160.0`.
Matched settings, isolated source copies, alternating baseline/candidate order, one attempt per profile.
Source/acceptance hashes and stop rules: [frozen manifest](codex-luna-pilot-v3/manifest.json).
Raw outcomes: [run records](codex-luna-pilot-v3/runs.jsonl); [analysis](codex-luna-pilot-v3/analysis.json).

7 runs; 3 complete pairs; 7/7 passed independent acceptance,
full regression suite, and patch scope. Optional adoption: 0/2 complete optional pairs.
Forced calls are execution controls, excluded from voluntary-adoption and efficacy interpretation.
In the forced pair, Luna said the advice did not change its implementation approach.
Optional pairs with no local decisions measure profile overhead and ordinary run variability;
their numerical differences do not establish an effect of Laya model inference.

| Task | Mode | Baseline seconds | Laya seconds | Time delta | API-equivalent delta | Decisions / accepted | Checks baseline / Laya |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| warm_timeout | forced | 70.03 | 78.36 | +11.9% | +32.2% | 1 / 1 | True / True |
| client_timeout | optional | 37.66 | 40.89 | +8.6% | +9.7% | 0 / 0 | True / True |
| choice_descriptions | optional | 33.60 | 32.61 | -2.9% | +3.8% | 0 / 0 | True / True |
| integration_modified | optional | — | 63.839 | — | — | — | incomplete |
| strict_saved_json | forced | — | — | — | — | — | incomplete |
| batch_error_ids | optional | — | — | — | — | — | incomplete |

Token usage is from Codex `turn.completed` events. Input counts aggregate model requests,
including repeatedly cached context. They are not unique prompt lengths or subscription charges.
Actual billed USD and subscription credit cost remain unknown. An illustrative API-equivalent total
is $0.0325, using public Luna input/cached-input/output rates
of $0.10/$0.01/$0.50 per million tokens, checked 2026-10-06. Cache writes and unreported billing
adjustments are excluded. This is not money spent or saved. [Official GPT-6 Luna pricing](https://developers.openai.com/api/docs/models/gpt-6-luna).
Including 5 excluded completed infrastructure attempts, the same illustrative total
is $0.0629. Interrupted attempts without a final
usage event have unknown usage and are excluded from this total, not counted as zero.

Whole-task timing includes Codex startup, tool calls, task repairs, and agent-run tests.
Independent grader tests run afterward and are excluded from task time identically in both profiles.
The local model was externally warm in all runs. No prewarm-on/off or cold-start comparison was made.
Worker request/accepted counters verify local decisions; each candidate also logs wrapper calls.
Patches remain in isolated workspaces; no trial patch was applied to production source.

Checkpoint cleanup moved the final workspace trees and launch wrappers into verified [workspace archives](trial-archives.md). Raw events, prompts, usage, checks, manifests, and predictions retain their original files; historical workspace paths in transcripts refer to those archived trees.

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
