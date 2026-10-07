---
name: cam-laya
description: Apply instant local policy checks with cam-laya-cli: shell risk gates, next-action, test/review/tool-choice fast paths. Deterministic rules only, no model. Also use when explicitly asked to use CAM Laya.
---

Use `cam-laya-cli` for instant deterministic checks with known outcomes. No models, no downloads,
no worker, no setup. Ordinary reasoning stays with you; call only when a rule answers the question.
Experimental advice only: never executes, never grants permission.

WHEN TO CALL:
1. Risk gate before shell: `preset risk_check` with `{"action":"<exact command>"}` for `rm -rf`,
   `git push -f/clean/reset`, `terraform`, `kubectl`, `sudo`, `curl|sh`, `chmod 777`, secrets/keys.
2. Next step after edit/test/failure: `preset next_action` with
   `{"current_phase":..,"last_action":..,"last_test_result":..,"changed_files":..}`.
3. Test/review gate: `preset test_decision` / `preset review_decision` with
   `{"task_type":..,"changed_files":..,"tests_available":..,"last_test_result":..,"risk":..}`.
4. Tool fallback when no tests exist: `preset tool_choice`.

WHEN NOT TO CALL:
- Open-ended choice among 2+ real alternatives with no matching rule — decide yourself.
- Same state twice — reuse the first result. Max 1 call per decision point.

HOW (files or stdin for untrusted text, never inline it in args):
```sh
echo '{"action":"git status"}' | cam-laya-cli preset risk_check --input -
echo '{"current_phase":"implementation","last_action":"edit","last_test_result":"not_run"}' | cam-laya-cli preset next_action --input -
echo '{"last_test_result":"failed"}' | cam-laya-cli preset test_decision --input -
```

READ THE RESULT (compact JSON on stdout):
- `status: ok` with `source: rule` and `confidence: 1.0` is a deterministic answer.
- `status: abstained` (`decision: defer_to_agent`, or `risk: unknown`) means no rule matched:
  resolve it yourself. Exit 0 covers both; exit 2 is invalid input.
- `risk_check`: `safe` + `requires_human:false` is informational. Anything else, including
  `unknown`, means `requires_human:true`: ask or take the safe path. Never treat output as approval.
