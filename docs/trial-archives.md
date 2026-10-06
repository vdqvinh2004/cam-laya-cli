# Trial evidence archives

The efficiency investigation is closed. Results remain in [Luna pilot](codex-luna-pilot-results.md), [filtering screen](offload-screen-results.md), and [local implementation results](local-results.md).

Raw prompts, JSONL events, usage records, test output, labelled corpora, predictions, frozen manifests, original source ZIPs, and reports retain their existing files. Final patched workspaces and launch wrappers are compressed below. Each archive was CRC checked and every member SHA-256 compared with its original bytes before deletion; archive inventory JSON records member hashes and symlink targets. Raw evidence outside the removed directories was also checked unchanged.

| Archive | Members | Compressed bytes | Checksums and inventory |
| --- | ---: | ---: | --- |
| [codex-luna-pilot/workspaces.zip](codex-luna-pilot/workspaces.zip) | 16 | 32,513 | [workspace-archive.json](codex-luna-pilot/workspace-archive.json) |
| [codex-luna-pilot-v2/workspaces.zip](codex-luna-pilot-v2/workspaces.zip) | 84 | 165,605 | [workspace-archive.json](codex-luna-pilot-v2/workspace-archive.json) |
| [codex-luna-pilot-v3/workspaces.zip](codex-luna-pilot-v3/workspaces.zip) | 120 | 234,543 | [workspace-archive.json](codex-luna-pilot-v3/workspace-archive.json) |
| [offload-screen/frozen-inputs.zip](offload-screen/frozen-inputs.zip) | 6 | 33,164 | [frozen-inputs-archive.json](offload-screen/frozen-inputs-archive.json) |
| [temporary-resources.zip](temporary-resources.zip) | 7 | 16,243 | [temporary-resources-archive.json](temporary-resources-archive.json) |

Workspace archives retain original `runs/TASK/PROFILE/workspace/` and `bin/` paths. Symlinks store their original target text. Only regenerable `.git`, `.ruff_cache`, and `__pycache__` directories were omitted. There are 13 archived trial workspaces; completed and interrupted attempts are both preserved. Their original absolute paths remain in historical transcripts.

The filtering input archive preserves exact source files matching the frozen screen manifest, including the pre-checkpoint README. The frozen offload runner and version 3 Codex runner are retained as `runner-source.py` in their respective result directories. Versions 1 and 2 are excluded infrastructure attempts; their manifests and events preserve available execution evidence.

Temporary resources retain the three stopped runtime/discovery directories and two marker/debug files removed from the system temporary directory. They contain cached-checkpoint configuration and diagnostic metadata, not model weights. Shared Hugging Face checkpoint files, the development environment, active client settings, and the prior Orca transcript were left in place.

Historical trial runners expect `/tmp/cam-laya-pilot-runtime-path` to name a runtime root containing `config/cam-laya-cli/config.json`. Manual reproduction requires restoring the archived pilot configuration into an owned temporary directory and writing that directory's path to the marker; cached checkpoint paths must be valid on the host. Use the runner from its original `benchmarks/` location. Trial commands remain explicit research operations; the normal CLI install/setup flow is documented in [README](../README.md).
