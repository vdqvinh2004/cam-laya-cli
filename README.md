# cam-laya-cli

Instant local policy checks through a portable shell interface. **Rules-only since 0.2.0: deterministic
presets, zero runtime dependencies, no models, no downloads, no worker.** The earlier model-backed
experiment is closed and measured; see [history](#history).

## Install

```sh
uv tool install .
cam-laya-cli status
cam-laya-cli doctor
```

No extras, no checkpoints, no network. Configuration: `$XDG_CONFIG_HOME/cam-laya-cli` (default
`~/.config`); state: `$XDG_STATE_HOME/cam-laya-cli` (default `~/.local/state`).

## Decide

```sh
cam-laya-cli preset test_decision --input examples/state.json
cam-laya-cli preset tool_choice --input examples/tool_choice.json
echo '{"action":"git status"}' | cam-laya-cli preset risk_check --input -
cam-laya-cli batch --input examples/presets.jsonl
```

Presets: `next_action`, `tool_choice`, `test_decision`, `review_decision`, `risk_check`. Each takes a
JSON object state (files or stdin; use `--input -` for stdin). Batch lines are full request envelopes
(`{"id":..,"preset":..,"state":{..}}`), evaluated independently in input order.

Known transitions answer deterministically (`source: rule`, `confidence: 1.0`). Anything without a
matching rule abstains: `decision: defer_to_agent` (or `risk: unknown` for risk checks) — resolve it
yourself. Hard-risk checks run locally. A non-safe risk result always requires human review.
This tool never executes recommendations and does not install command-blocking safety hooks.

Quote JSON with single quotes or files/stdin; unquoted `{...}` breaks in zsh (brace expansion).
`read-only`/`workspace-write` sandboxes used to block the old worker socket; 0.2.0 has no worker and
no socket, so sandboxed runs work unchanged.

## Results and failures

Stdout contains compact JSON; exit 0 means a valid response, **including abstention**. Inspect `status`
before branching. Exit 2 means invalid input. A batch returns the greatest error code encountered.

Inputs are bounded (64 KiB) and request text is never persisted. Duplicate JSON keys are rejected.

## Agents

```sh
cam-laya-cli install-agent codex --root /path/to/project
cam-laya-cli install-agent claude --root /path/to/project
cam-laya-cli install-agent opencode --root /path/to/project
cam-laya-cli uninstall-agent claude --root /path/to/project
```

Installers create project-scoped skills and nothing else: no hooks, no prewarming, no advice injection.
Existing skill files are merged by ownership digest; unowned or modified skill files are never
overwritten, and uninstall removes only unchanged owned assets. Upgrading from 0.1.x also removes
legacy prewarm hooks and plugins. `doctor` distinguishes configuration from live verification.

## Measure

```sh
cam-laya-cli benchmark --samples 100
```

Benchmark times in-process decisions plus fresh CLI processes over the deterministic probe. It reports
distributions only; provider tokens and billed charges do not apply to this tool by construction.

## Development

```sh
uv sync --python 3.12 --extra dev
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv build
```

Python 3.11+ with no runtime dependencies.

## History

Versions before 0.2.0 backed presets with a local MLX model behind a persistent worker. Paired studies
found no whole-task speed or cost saving and no voluntary agent adoption: see the [adoption pilot
report](docs/efficacy-pilot-report.md), [main efficacy results](docs/efficacy-main-results.md), [local
results](docs/local-results.md), and [evaluation protocol](docs/evaluation.md). 0.2.0 keeps the
deterministic rules that measured alive (299 guard cases, 12 legacy decisions) and removes everything
that did not: models, worker, setup/warm/prewarm, and the `route_task` and custom-question paths that
only ever worked through the model.
