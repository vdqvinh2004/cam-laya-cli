---
name: cam-laya
description: Choose tools, next actions, task routes, test and review steps, and shell risk levels with local CAM Laya when deciding among 2-6 defined alternatives would otherwise need extra reasoning. Batch typed choice, score, and yes/no decisions locally instead of extra model calls. Also use when explicitly asked to use CAM Laya.
---

Use `cam-laya-cli` to replace extra reasoning with one fast local call when you face concrete alternatives. Keep ordinary free-form coding with yourself; call only when it saves a separate reasoning step. Extra calls can increase work. Experimental advice only: never executes, never grants permission.

WHEN TO CALL (any one is enough):
1. Tool choice among the fixed set (`search, read, shell, edit, test, ask_user`): `preset tool_choice`. Custom tool sets use generic `decide` choice (2-6 options).
2. Next step or task route: state has `current_phase, last_action, last_test_result, changed_files, task_type`.
3. Test/review gate before running a suite or asking for review.
4. Risk gate before shell: exact command for `rm -rf`, `git push -f/clean/reset`, `terraform`, `kubectl`, `sudo`, `curl|sh`, `chmod 777`, secrets/keys.
5. Bounded classification that would otherwise be its own reasoning call.

WHEN NOT TO CALL:
- Single obvious action, open-ended design, or you already know the answer.
- More than 6 alternatives, vague criteria, more than 64 questions, or same state asked twice. Reuse the first result. Max 1 Laya call per decision point.
- Do not retry abstention/unavailable to force an answer. Fall back to your own judgment.

HOW (files or stdin for untrusted text, never inline it in args):
1. `cam-laya-cli status`. If unavailable, continue normally and never block. `setup` downloads weights; routine calls never do. Sandboxed runs need socket access: on `PermissionError`/`worker_unavailable` retry with workspace-write (plus socket dir) or outside the sandbox; do not mistake sandbox denial for abstention.
2. Tool choice (fixed set, `state` must be an object):
```sh
echo '{"current_phase":"debugging","last_test_result":"failed","changed_files":2}' | cam-laya-cli preset tool_choice --input -
```
Custom tool sets use generic `decide` (2-6 criteria):
```json
{"state":"Failing test touches auth.py; changed_files: 2.","questions":{"tool":{"type":"choice","instructions":"Choose the next tool.","criteria":{"search":"Search for usages first","read":"Read the file directly","shell":"Run the failing test"}}}}
```
```sh
cam-laya-cli decide --input request.json
```
3. Next step / route / test / review (presets, `state` must be an object):
```sh
echo '{"current_phase":"implementation","last_action":"edit","last_test_result":"not_run"}' | cam-laya-cli preset next_action --input -
echo '{"last_test_result":"failed"}' | cam-laya-cli preset test_decision --input -
```
4. Risk gate (always human-gated):
```sh
echo '{"action":"git status"}' | cam-laya-cli preset risk_check --input -
```
`safe` with `requires_human:false` is informational. Any other risk, `unknown`, or `unavailable` means `requires_human:true`: ask or pick the safe path yourself.
5. Batch related questions sharing one state in one call (`decide`), or multiple states in one connection (`batch --input requests.jsonl`, max 16 questions per forward pass, order and ids preserved). `--min-confidence` gates max option probability, not accuracy. `--details` only when debugging distributions.

READ THE RESULT:
- Stdout is compact JSON. Exit 0 includes abstention. Exit 2 invalid input, exit 3 unavailable.
- Check `status` then each answer: `ok` value is usable, `abstained` has `value:null` plus `reason_code` (`truncated_state|collapsed_options|uncalibrated_temperature|low_confidence`), `unavailable` means resolve yourself. `abstention: unevaluated` means no threshold was set.
- `source:rule` is deterministic (`confidence:1.0`); `source:model` has `model:{name,id,revision}`, `confidence` entropy-based, `answer_confidence` max prob, `calibration:unvalidated_for_workload`. Raw predictions under `details` only.
- Preset fallback is `decision:defer_to_agent` (or `risk:unknown`): do not treat as approval.
