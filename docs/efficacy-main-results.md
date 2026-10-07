# Main efficacy results: no efficacy (first paired measurement)

Date: 2026-10-08. Design: [evaluation protocol](evaluation.md). Adoption pilot: [pilot report](efficacy-pilot-report.md).

## Design (frozen before runs)

12 held-out micro-tasks from two pinned repos (`more-itertools@81c21a8`, `six@c8e3940`):
8 discovery (symptom-only injected bug) + 4 bypass (explicit file/function target). Every task has an
independent executable check (repo pytest nodes, or frozen assertions where the repo suite collects
nothing) and a patch scope (source file only; tests forbidden). 4 counterbalanced baseline/skill pairs
per task (order B→C, C→B, B→C, C→B) on one client first: OpenCode v2.0.24, `opencode-go/claude-haiku-5-5`.
Prompts identical; skill presence is the only difference. Package `cam-laya-cli@c69c212`, worker warm,
per-run timeout 300 s, tripwire cap $4.50. Full manifest + per-run JSONL retained outside the repo
(`/tmp/laya-main/`); exclusions frozen (>10% excluded invalidates).

Harness lessons during setup (kept, not hidden): opencode resolves its project from `$PWD`, not the
client's OS cwd — the runner forces `PWD` to the worktree; agents are confined to their worktree with
a transcript audit for cross-task reads (0 hits); `PYTHONDONTWRITEBYTECODE=1` + pycache purges on every
reset after a stale-bytecode false signal was caught in validation.

## Execution integrity

96/96 runs recorded, 0 excluded, 48/48 complete pairs, 0 contaminated transcripts.
Study spend: **$0.32** (cap $4.50 untouched).

## Results

| Task | Δtime med (cand−base) | Δcost med | pass base | pass cand | CLI calls (cand) |
|------|----------------------|------------|-----------|-----------|------------------|
| D1 | −2.85 s | +$0.00047 | 4/4 | 4/4 | 0 |
| D2 | −2.30 s | +$0.00027 | 4/4 | 4/4 | 0 |
| D3 | −2.30 s | −$0.00028 | 4/4 | 4/4 | 0 |
| D4 | −0.80 s | +$0.00039 | 4/4 | 4/4 | 0 |
| D5 | −0.20 s | −$0.00013 | 4/4 | 4/4 | 0 |
| D6 | +0.10 s | −$0.00013 | 4/4 | 4/4 | 0 |
| D7 | +1.30 s | +$0.00030 | 4/4 | 4/4 | 0 |
| D8 | −1.30 s | +$0.00023 | 4/4 | 4/4 | 0 |
| B1 | −1.35 s | −$0.00010 | 4/4 | 4/4 | 0 |
| B2 | +0.00 s | −$0.00010 | 4/4 | 4/4 | 0 |
| B3 | −0.95 s | +$0.00056 | 4/4 | 4/4 | 0 |
| B4 | +5.20 s | +$0.00523 | 4/4 | 4/4 | 0 |
| **pooled** | **−0.05 s, 95% CI [−1.60, +0.90]** | **+$0.00018, 95% CI [−0.00006, +0.00056]** | **48/48** | **48/48** | **0/48 runs** |

CIs are cluster-bootstrapped by task (10k resamples). Deltas scatter both directions at the scale of
run-to-run noise; neither CI sits below zero, let alone at −10%.

## Verdict: no efficacy

Quality gates pass trivially (100%/100% — ceiling effect of micro-tasks), but there is no time or cost
signal: the skill was never invoked in 48 candidate runs, so candidate runs *are* baseline runs plus an
unread skill file. Unforced adoption for "fix this failing check" tasks is zero; the pilot showed agents
do call Laya when the prompt frames an explicit decision among alternatives. Nothing here justifies
automatic branching or any speed/cost claim. This matches and now measures the repo's standing position.

## Limitations and what could change the answer

Micro-tasks with 100% solvability; one client, one cheap model, unmentioned skill; cost deltas are
sub-cent noise by construction. A fairer test would need harder tasks (no ceiling), decision-framed
prompts or forced-skill arms, and other clients — each expanding spend past this study's cap.
Revisit only with a fresh frozen manifest and its own approved budget.
