---
name: cam-laya
description: Classify bounded text or batch typed choice, score, and yes/no decisions with local CAM Laya when those decisions would otherwise require separate model calls. Also use when explicitly asked to use CAM Laya.
---

Use `cam-laya-cli` for bounded classifications with defined alternatives. Batch related questions sharing a state in one call. Keep ordinary coding reasoning with the coding agent; extra decision calls can increase work.

1. Run `cam-laya-cli status`. If runtime is missing, report availability and continue ordinary work. Explicit model provisioning uses `setup`; routine decisions never download weights.
2. Write request JSON with `state` and `questions`, then call `cam-laya-cli decide --input request.json`. Use files or stdin for untrusted text, preserving shell quoting.
3. Inspect `status` and each answer's `status`. Use accepted values as experimental advice. Abstention or unavailable means the coding agent resolves the decision.

Example request:

```json
{"state":"Build reports ModuleNotFoundError for requests.","questions":{"category":{"type":"choice","instructions":"Classify this failure.","criteria":{"dependency":"Missing package","syntax":"Invalid source syntax","other":"Insufficient evidence or another problem"}}}}
```

`score` uses ordered text criteria; `noul` returns P(true). `--min-confidence` gates maximum option probability, not empirical accuracy. Truncation and affected calibration diagnostics abstain. Validate the exact workload before automatic branching. Recommendations never grant permission or execute commands.

`batch --input requests.jsonl` reuses one worker connection for multiple states. `preset NAME --input state.json` exposes experimental coding policies; deterministic answers identify `source: rule`. `--details` loads distributions only when needed. Exit 0 includes abstention; exit 2 is invalid input; exit 3 is unavailable.
