# cam-laya-cli

Local Laya typed decisions through a portable shell interface. **Experimental: no whole-task speed or billed-cost saving has been demonstrated.** Runtime v1 requires Apple Silicon and macOS 14+; any agent with local shell access can use it.

The efficiency investigation is closed. Keep this tool opt-in; agent skills and session warming require explicit installation. See the [investigation status](docs/efficiency-status.md), [Luna pilot](docs/codex-luna-pilot-results.md), [filtering screen](docs/offload-screen-results.md), and [evidence archives](docs/trial-archives.md).

## Install

```sh
uv tool install --python 3.12 '.[mlx]'
cam-laya-cli setup
cam-laya-cli warm
cam-laya-cli doctor
```

Setup provisions the pinned English checkpoint and separate `cam-laya-cli` configuration. It installs no agent integration. Model files use the shared Hugging Face cache; routine decisions are offline. Provision other languages explicitly with `setup --model multilingual`; provision the specialized checkpoint with `setup --model typed-decisions`. Automatic routing returns unavailable if its selected checkpoint is missing.

Base installation (`uv tool install .`) supports rules, diagnostics, integration management, and unavailable-model responses without MLX. Install the MLX extra to run custom questions.

## Decide

```sh
cam-laya-cli decide --input examples/request.json
cam-laya-cli preset test_decision --input examples/state.json
cam-laya-cli batch --input examples/requests.jsonl
```

Custom JSON contains `state` (text, object, or conversation list) and `questions`. Questions use the upstream `choice`, ordered `score`, or `noul` type (`noul` is P(true), not a permission). Optional request fields: `id`, `model`, `min_confidence`. Use `--input -` for stdin, `--details` for distributions, and `--timeout` to change the 60-second default.

JSONL batches accept the same request envelope, including `preset` instead of `questions`. Different states execute serially on one connection. Questions sharing a state use native MLX question batching (16 per forward pass). Results preserve input order and IDs; invalid records report their line number and do not discard later records. Empty lines are invalid records.

Coding presets: `route_task`, `next_action`, `tool_choice`, `test_decision`, `review_decision`, `risk_check`. Known transitions use deterministic rules; unresolved advice uses Laya and is experimental. Hard-risk checks run locally. A model risk result always requires human review. This tool never executes recommendations and does not install command-blocking safety hooks.

Quote JSON with single quotes or files/stdin; unquoted `{...}` breaks in zsh (brace expansion) and double quotes need escaping. Prefer heredoc files for multi-line states: `cat > request.json <<'EOF' ... EOF`. Sandboxed agents need socket access: `read-only`/`workspace-write` sandboxes block the private worker socket (`PermissionError`, exit 3). Retry with workspace write plus the socket dir or outside the sandbox; never mistake sandbox denial for abstention.

## Results and failures

Stdout contains compact JSON; exit 0 means a valid response, **including abstention**. Inspect `status` and individual answer statuses before branching. Exit 2 means invalid input; exit 3 means runtime, transport, or model unavailable. A batch returns the greatest error code encountered.

`confidence` is entropy-based for choice/score and maximum probability for noul. `answer_confidence` is maximum option probability; neither is measured accuracy. `--min-confidence` gates on `answer_confidence`. With no threshold, `abstention: unevaluated` makes that explicit. Truncated state, collapsed options, and affected clamped temperature buckets abstain even without a threshold. Raw diagnostic predictions remain under `details` only when requested; they are not validated decisions. Model token usage describes local model processing, not provider-billed tokens.

Inputs and responses are bounded. JSON duplicate keys and non-finite numbers are rejected. Request text is neither persisted in metrics nor placed in shell arguments. The worker serializes inference and caches weights, not decision results; switching checkpoints may reload weights. Socket and state directories are private. An idle worker exits after 30 minutes.

## Agents and opt-in prewarming

```sh
cam-laya-cli install-agent codex --root /path/to/project
cam-laya-cli install-agent claude --root /path/to/project --prewarm
cam-laya-cli install-agent opencode --root /path/to/project --prewarm
cam-laya-cli uninstall-agent claude --root /path/to/project
```

Installers create project-scoped skills. `--prewarm` adds session-start warming only; it injects no advice. Client hook trust and permissions still apply. Existing settings are merged and backed up; unowned skill/plugin files are not overwritten. Uninstall removes only unchanged owned assets and exact owned hook entries. Modified owned assets are kept and reported. `doctor` distinguishes configuration from live verification.

Codex and OpenCode are installed on the development host. Claude Code is absent. No live agent compatibility or efficacy claim follows from installer checks.

## Measure

```sh
cam-laya-cli benchmark --samples 100 --output docs/local-rules.json
cam-laya-cli benchmark --input examples/request.json --output docs/local-model.json
cam-laya-cli stats
cam-laya-cli stop
```

Benchmark reports first call, persistent IPC, fresh CLI processes, direct engine execution, output size, memory, and sample distributions. `benchmarks/compare_transport.py` provides a benchmark-only MCP adapter over the same worker. `benchmarks/evaluate.py` checks guard rules and the frozen local decision corpus. See [feasibility](docs/feasibility.md), [evaluation protocol](docs/evaluation.md), and [local results](docs/local-results.md).

No paid agent trials run automatically. Those require the frozen protocol and a separately approved budget. Reduced JSON bytes are not evidence of lower provider token charges.

## Development

```sh
uv sync --python 3.12 --extra mlx --extra benchmark --extra dev
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv build
```

Python 3.11+ base package has no runtime dependencies. Optional MLX is pinned to 0.3.0. Checkpoint revisions and all resolved dependencies are pinned in source and `uv.lock`. Configuration: `$XDG_CONFIG_HOME/cam-laya-cli` (default `~/.config`); state: `$XDG_STATE_HOME/cam-laya-cli` (default `~/.local/state`). Long socket paths use a private, configuration-specific directory under `/tmp`.
