# CLI-first Laya integration feasibility

Date: 2026-10-06

## Decision

A CLI is feasible as the primary Laya interface for Codex, Claude Code, and OpenCode, because all three provide shell access in their local coding-agent workflows. Expect clearer agent discovery and fewer added tool definitions when MCP tools are otherwise loaded eagerly. Do not expect a CLI by itself to make inference faster or cheaper: both interfaces still reach the same decision model, and a one-shot CLI can add process startup cost.

Keep one decision engine and route model advice through a narrow CLI surface. Retain deterministic rules for clear decisions; invoke Laya only when advice can change the next action. Do not add an unconditional classifier call before each advice request. Keep a thin MCP adapter only if MCP-only clients remain an actual target. Treat this as a portability and adoption change until a paired evaluation shows a performance, quality, or cost gain.

No paid API trials or new agent performance trials were run for this report. It combines primary documentation with the stopped MCP project's recorded experiments. No universal savings claim follows.

## What the stopped project measured

The source baseline is commit [e73ff6e](https://github.com/vdqvinh2004/cam-laya-mcp/tree/e73ff6e). Its README records four negative assistance experiments and chooses guard-only as the default.

| Evidence at e73ff6e | Result | What it supports |
| --- | --- | --- |
| Small decision screen | Deterministic rules matched 12/12 labels; raw Laya-MLX matched 4/12. The source calls this a small screen, not a general accuracy claim. | Keep clear transitions on rules; validate model advice on a larger held-out set before enabling automatic decisions. |
| Warm advice calls | Every observed warm model call returned defer-to-agent after 0.1–0.4 s inference. One cold tagged review call took 36.88 s to load the model, 0.38 s for inference, and 37.74 s total in the client. | Avoid routine calls that cannot change the agent's action; report cold and warm costs separately. |
| First Codex comparison | One paired run per five prompts used 25.2% more total tokens and was 33.3% slower by median with Laya enabled. It made four MCP calls. Actual billed cost was unavailable. | This is a warning signal, not a stable estimate: the sample was tiny and prompts tested availability more than coding quality. |
| Paired coding screen | The eligible 15-pair cohort passed 15/15 checks in each profile. The combined profile was 3.76 s slower by paired median; its time interval crossed zero. The full 30-pair screen was 4.515 s slower, with a paired 95% interval of +3.425 to +7.805 s. The paired token delta interval crossed zero. No coding run called MCP or produced a model decision. | Existing evidence does not establish a CLI-vs-MCP effect or a coding benefit; the coding screen did not exercise either decision interface. |
| Retrieval and hook adoption | Guided retrieval pilots made zero calls to the optional retrieval tool. A separate context pilot hit 2/4 live discovery targets and was stopped. A PreToolUse+PostToolUse profile added 17,469 paired median tokens, with a 95% interval of +16,476 to +33,651. | The adoption and hook behavior need their own measurements; registering a tool does not make agents use it. |

Sources: [e73ff6e README](https://github.com/vdqvinh2004/cam-laya-mcp/blob/e73ff6e/README.md), [Codex efficacy report](https://github.com/vdqvinh2004/cam-laya-mcp/blob/e73ff6e/docs/codex-efficacy-baseline.md), and [release readiness](https://github.com/vdqvinh2004/cam-laya-mcp/blob/e73ff6e/docs/release-readiness.md).

## CLI and MCP tradeoffs

**Context and token cost.** Anthropic documents tool names, descriptions, schemas, tool calls, and results as token-bearing input; OpenAI prompt caching also includes tool definitions in the stable prefix. A CLI usually adds command text and stdout/stderr to the existing shell tool rather than adding a dedicated schema. This may reduce context when many MCP schemas are loaded upfront. However, Claude Code and OpenAI Agents support deferred MCP tool discovery; Claude Code currently defers MCP definitions by default on supported configurations. Stable schemas can also benefit from prompt caching. Measure provider usage counters instead of treating MCP's JSON-RPC wire framing as model tokens: the host handles that protocol and sends tool content to the model. [Anthropic tool-use pricing](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [Claude Code MCP search](https://code.claude.com/docs/en/mcp), [OpenAI tool search](https://developers.openai.com/api/docs/guides/tools-tool-search), [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

**Startup and latency.** MCP stdio launches a local server subprocess and keeps it attached to the client transport. A CLI invoked once per decision may start a new process each time; an interactive process or daemon can reuse loaded state. Neither protocol guarantees a latency win. Reuse the existing resident model process where possible, and separate command startup, daemon/model cold load, inference, and total agent-turn time in measurements. [MCP transport specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [MCP TypeScript client lifecycle](https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-client.html).

**Composition and output.** A single CLI command can batch requests and use JSON/JSONL output; upstream Laya documents both batch prediction and JSON output. MCP tools can also accept batches and return structured content, so batching and compact results are available on either surface. Changing the invocation syntax alone does not remove an agent/model turn. [Upstream Laya CLI and MCP guide](https://github.com/NandhaKishorM/laya/blob/main/docs/cli-mcp.md), [MCP tool schemas and outputs](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

**Portability and safety.** Codex, Claude Code, and OpenCode document local shell access, but it can be restricted per session or agent. A CLI must be installed in the same environment as the agent and allowed by its shell policy. MCP offers a typed interface with narrower arguments and a standard discovery contract, and can work for clients without shell access. Use stdin or a file for task text rather than interpolating untrusted text into shell syntax; return concise structured output and keep the command read-only. [OpenAI shell](https://developers.openai.com/api/docs/guides/tools-shell), [Claude tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [OpenCode tools and permissions](https://docs.opencode.ai/docs/tools/), [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## Laya capability limits

Upstream Laya presents its CLI and stdio MCP server as adapters over the same Router, with matching typed decisions, batch paths, JSON output, and prediction hooks. That supports reusing a shared engine rather than maintaining two implementations. Upstream application benchmarks vary by workflow: its listed support-triage results are about 0.50–0.52 accuracy, while some other tasks score much higher. These benchmarks do not establish usefulness for coding-agent transitions, and hardware timings do not isolate CLI from MCP. Evaluate the exact decision questions and labeled states used here. [Laya CLI/MCP guide](https://github.com/NandhaKishorM/laya/blob/main/docs/cli-mcp.md), [Laya benchmark report](https://github.com/NandhaKishorM/laya/blob/main/BENCHMARKS.md).

## Recommended evaluation

Keep transport and model policy as separate comparisons:

1. **Adapter parity:** Run identical requests through CLI and MCP against the same resident engine, checkpoint, settings, and output fields. Include cold-start and warm-call runs. Check decision parity, command failures, and whether the agent used the result correctly.
2. **Policy value:** Compare no Laya, deterministic rules only, model advice on demand, and rules followed by Laya only when rules defer. Track decision accuracy, useful coverage, defer rate, coding-quality checks, and whether the recommendation changed the result.
3. **Host adoption:** Test Codex, Claude Code, and OpenCode with normal prompts and each host's ordinary permissions. Also run a forced-call control to separate discoverability from execution speed. Report shell-unavailable or permission-denied cases rather than generalizing from the three hosts to all agents.
4. **Cost and performance:** Record paired wall time, first useful response, input/cached-input/output tokens, tool turns, CLI startup, model load, inference time, and failures. Capture billed API cost only when the provider exposes actual usage or billing; keep API-equivalent estimates labeled as estimates.

The prior release gate requires at least 10% lower median time on the eligible paired cohort, with the paired confidence interval excluding zero, before claiming a speed gain; it also requires no coding-quality regression. Require measured billed savings before claiming a cost gain. If the CLI improves adoption but misses those gates, describe the result as improved availability or integration, not performance or cost efficiency. [Prior release gates](https://github.com/vdqvinh2004/cam-laya-mcp/blob/e73ff6e/docs/release-readiness.md).
