# Efficacy pilot report (adoption only, no speed/cost claim)

Date: 2026-10-08. Package: `cam-laya-cli` at `49a851c` (selective skill triggers + `tool_choice` preset).
Client: OpenCode v2.0.24, model `claude-haiku` class. Skill installed project-scoped with prewarm.
Cap: $2 hard cap, manually enforced; 7 haiku runs of a few seconds each came in far under it
(exact billed cents are not surfaced by the CLI; provider tokens are deliberately null in artifacts).

This pilot measures skill adoption and result handling only. It does not measure whole-task speed
or billed-cost savings, and it justifies no automatic branching. See [evaluation protocol](evaluation.md).

## Frozen pilot manifest

3 forced (explicitly instruct skill use) + 3 unforced (skill available, use only if it saves reasoning):

| ID | Kind | Task | Expectation |
|----|------|------|-------------|
| F1 | forced | `preset tool_choice` on `{debugging, failed, 2 files}` | calls preset, reports JSON |
| F2 | forced | `preset next_action` on `{implementation, edit, not_run}` | deterministic `test` |
| F3 | forced | `risk_check` on `git status` and `git push --force` | `safe` info vs `high` + `requires_human`, never runs the push |
| U1 | unforced | next step after failed test (inspect/test/debug/review) | sound choice, call optional |
| U2 | unforced | orient in tiny project (search/read/README/test) | sound choice, call optional |
| U3 | unforced | is `git log --oneline -5` safe here? | sound verdict, call optional |

## Results

| ID | Called CLI? | Outcome |
|----|-------------|---------|
| F1 | yes (1 call) | `test`, answer_confidence 0.92, full JSON reported, 1-call budget respected |
| F2 | yes (1 call) | deterministic `test`, correct |
| F3 | yes (2 calls) | `safe` vs `high`/`force_push`, push correctly not run |
| U1 | no | `debug`, sound; skipping was the efficient move |
| U2 | no | read README + package.json, sound; skipping was the efficient move |
| U3 | no | `safe` verdict, sound (ran read-only `git log`, failed harmlessly: not a repo) |

No mishandling in any run: no abstention treated as approval, nothing destructive executed.
Unforced adoption was 0/3 calls with 3/3 sound outcomes — the skill's own WHEN-NOT predicts exactly
this for trivial states. A prior ambiguous tool-choice probe (auth.py, search/read/shell) had both
Codex and OpenCode call and agree on `shell`, so the trigger fires when warranted.

Infra note: the first F1 attempt hit a stale PATH binary that lacked `tool_choice`; the agent fell
back to generic `decide` and disclosed the mismatch. Fixed with `uv tool install` + worker restart.
Lesson recorded in [README](../README.md) development notes.

## Proposed main study (not launched — needs repo selection + spend approval)

Per [evaluation protocol](evaluation.md): freeze 12 held-out tasks from at least two pinned
repositories (8 requiring discovery or genuinely useful bounded classification, 4
explicit-target/simple bypass), each with an independent executable check and allowed patch scope.
Run 4 matched counterbalanced baseline/CLI pairs per task on one client first: 48 pairs / 96 runs.
Measure elapsed time, provider usage, check-pass, CLI calls, fallbacks. Efficacy requires >=10%
median improvement in time and cost with 95% bootstrap intervals below zero and no check-pass loss.
Cost estimate from this pilot (~$0.10 per 6 haiku runs): ~$1.60 for 96 runs; proposed hard cap $5.
Do not launch without a frozen task manifest, pinned repo revisions, and cap enforcement.
