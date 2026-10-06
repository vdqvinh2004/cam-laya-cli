# Local implementation and evaluation results

Date: 2026-10-06. Package: `cam-laya-cli` 0.1.0. Historical source: sibling `cam-laya-mcp` at `e73ff6e`, left unchanged.

## Conclusion

The CLI is functional, with a resident local model worker, typed questions, JSONL batches, deterministic coding presets, and project-scoped Codex/Claude/OpenCode skills. Prewarming is optional and injects no advice. The base package has no runtime dependencies; MLX and the benchmark-only MCP adapter are separate extras.

**Changing MCP to a CLI did not produce a local latency win against persistent MCP. Whole-task speed and provider cost savings remain unproven.** For the short model request, fresh CLI median was 50.237 ms; persistent MCP median was 26.358 ms in a separate counterbalanced adapter experiment. Python process startup outweighed the small adapter saving. Batching amortizes process startup but has not been tested for whole-task agent benefit.

This is an experimental interface release. All-agent compatibility is not established: runtime v1 targets Apple Silicon, requires local shell access, and has not been exercised in live agent sessions. Model confidence is not validated accuracy or authorization.

## Environment and provenance

- Host: macOS 27.0.1, arm64; Python 3.12.14; `laya-mlx` 0.3.0; benchmark MCP SDK 2.3.0. Dependencies: `uv.lock`.
- Measured checkpoint: `aac6fef/laya-mlx`, revision `20aed815fc6acde75733882e7ec0e3f28aeb9717`. Multilingual and specialized checkpoints are supported but were not measured.
- Existing cached English weights were reused. Setup and integration checks used disposable XDG/project directories. No active client configuration was changed.
- No paid APIs or live agent trials ran. Provider usage and billed USD are deliberately null in artifacts.
- Codex and OpenCode binaries exist on this host; Claude Code is absent. Installer checks do not establish live compatibility.

## Transport and startup

Each warm measurement below contains 100 samples. Values are milliseconds; distributions and individual samples are retained.

| Short request / path | Median | p95 | Artifact |
| --- | ---: | ---: | --- |
| Model, fresh CLI process | 50.237 | 53.876 | [Model benchmark](local-model.json) |
| Model, persistent IPC client | 24.061 | 25.055 | [Model benchmark](local-model.json) |
| Model, direct independent engine | 23.541 | 24.324 | [Model benchmark](local-model.json) |
| Fresh CLI time outside worker engine | 25.987 | 26.775 | [Model benchmark](local-model.json) |
| Same-worker counterbalanced IPC | 24.709 | 25.450 | [Adapter comparison](local-transport.json) |
| Same-worker counterbalanced MCP | 26.358 | 27.629 | [Adapter comparison](local-transport.json) |
| Deterministic preset, fresh CLI | 25.727 | 29.271 | [Rules benchmark](local-rules.json) |
| Deterministic preset, persistent IPC | 0.177 | 0.314 | [Rules benchmark](local-rules.json) |

The model benchmark began with no worker and cached files: first call 1,342.343 ms, including worker startup and model load. Worker RSS was 907,184 KiB (about 886 MiB); repeated calls recorded one model load. Rules timing reused a running worker and is not a cold-start measurement. Memory is a snapshot, not a peak comparison. Direct-engine measurement loads an independent engine in the benchmark process; its memory is reported separately.

MCP initialization took 286.185 ms. Adapter experiment alternated IPC/MCP and MCP/IPC order over the same worker and returned identical outputs after excluding timing fields. IPC saved about 1.65 ms at the median relative to this MCP adapter. That measurement excludes fresh CLI process startup and client/model-visible discovery context. It cannot establish a token saving or quantify the prior project's client overhead.

Fresh CLI non-engine time is calculated per sample as elapsed command time minus returned worker engine time, including shell client/IPC/output overhead. It is not a subtraction of independent percentiles. Both frozen local latency targets passed (non-engine p95 <=50 ms; complete short-request p95 <=250 ms). These targets are responsiveness checks, not evidence of productivity improvement.

## Decision screen

The [frozen protocol](evaluation.md) uses 180 hand-authored synthetic cases: 60 development and 120 held-out, with disjoint source groups. Labels precede predictions. The [corpus checksum](../benchmarks/corpus.sha256) and [per-case predictions](local-decisions.json) are retained. This is not deployment validation or a public production benchmark.

Development alone selected the maximum-coverage threshold achieving at least 95% observed accepted accuracy, with stricter ties. No runtime default threshold was added.

| Held-out workload | Raw model correct | Development threshold | Accepted correct / accepted | Coverage | Rules correct / accepted | Hybrid correct / accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Excerpt relevance | 40/40 | 0.5 | 40/40 | 100% | 0/0 | 40/40 |
| Task routing | 37/40 | 0.5 | 36/38 | 95% | 38/38 | 40/40 |
| Error triage | 39/40 | 0.8 | 33/33 | 82.5% | 28/30 | 34/36 |

Routing accepted accuracy was 94.74%, below the development target. Triage rules introduced errors; the hybrid did worse than accepted model-only predictions. Simple rule fallback therefore does not guarantee better decisions. Median measured call latencies were 26.228, 43.543, and 42.071 ms respectively. Six of 90 paired option-order/framing variants changed the selected value.

Twelve extra negation/control/paraphrase diagnostics were authored **after** the initial synthetic screen; they are separate from the frozen corpus and never tune its thresholds. Ten were correct. Two requests saying not to cancel were misclassified as cancellation, with maximum option probabilities 0.5332 and 0.5649. These failures prevent interpreting an unrestricted classifier as an authority to act.

The [real-model smoke check](local-smoke.json) exercised choice, score, and noul; eight simultaneous clients and eight fresh CLI processes reused one model load. Oversized token states abstained. The inherited 12-option routing question also abstained because its native temperature bucket was clamped. Raw diagnostics are available only with `--details`; automatic advice hooks remain absent.

## Correctness and packaging

- Ten unittest checks passed, covering validation, abstention, unavailable models, output contracts, integration ownership, concurrent startup, private sockets, JSONL recovery, metrics privacy, and diagnostics without startup.
- All 299 inherited guard cases and 12 inherited deterministic decisions passed. These guards are pattern-based checks, not a shell sandbox.
- Ruff passed; wheel and source distribution built. Wheel includes the skill asset, LICENSE, and NOTICE.
- A fresh environment installed the wheel with `--no-deps`, outside the source tree. Doctor, deterministic decisions, missing-model exit 3, installation/uninstallation for all three clients, and generated OpenCode JavaScript syntax passed. MLX and MCP were absent.

## Reproduce

Use disposable configuration/state directories for evaluation. Setup may download model files; routine inference uses pinned local files.

```sh
uv sync --python 3.12 --extra mlx --extra benchmark --extra dev
export XDG_CONFIG_HOME="$(mktemp -d)"
export XDG_STATE_HOME="$(mktemp -d)"
uv run cam-laya-cli setup --model english
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv build
uv run cam-laya-cli stop
uv run cam-laya-cli benchmark --samples 100 --input examples/request.json --output /tmp/local-model.json
uv run python benchmarks/compare_transport.py --input examples/request.json --samples 100 --output /tmp/local-transport.json
uv run python benchmarks/evaluate.py --model --robustness --output /tmp/local-decisions.json
uv run cam-laya-cli benchmark --samples 100 --output /tmp/local-rules.json
uv run cam-laya-cli stop
```

Keep full outputs, not just favorable summaries. A future paid comparison requires a frozen task manifest, approved budget, paired quality checks, actual provider usage, and the gates in [evaluation.md](evaluation.md). It is deferred; no speed or cost claim is made by this implementation.
