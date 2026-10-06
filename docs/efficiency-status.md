# Efficiency investigation status

Broad coding-agent trials are paused at the user's request. No general coding trial or paid main study is running. The existing CLI remains experimental.

The local evidence-filtering screen is complete. Its [manifest](offload-screen/manifest.json) and checksum froze eight queries, actual project documents and captured failure logs, 25 labelled evidence spans, chunking, confidence threshold, fallback behavior, search baselines, and the eligibility gate before predictions. No new model download or Codex inference was part of this screen.

A further GPT-6 Luna paired pilot is conditional on all labelled evidence surviving, at least 50% of passage-body bytes being removed, at least 10 percentage points more reduction than the best tested evidence-preserving baseline, and no runtime errors. Failed or uncertain classifications keep the passage. There is no threshold tuning or retry to make the gate pass.

The gate failed: Laya retained 17/17 labelled evidence chunks but removed only 4.6% of input bytes. Search/rules removed more input but lost required evidence. The conditional Luna pilot was skipped. Further Laya efficiency work for this investigated workflow is stopped. [Results and limitations](offload-screen-results.md) and the [decision record](offload-screen/decision.json) preserve all outcomes. No trial or screen remains running.

Checkpoint closure: findings and raw predictions remain available; disposable source workspaces and stopped runtime configurations were archived before cleanup. The CLI remains experimental and opt-in. [Archive inventory and checksums](trial-archives.md) document preservation. Revisit only for a specific real workload with measured expensive classification that Laya can replace.
