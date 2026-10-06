# Local evidence-filtering screen

**Conclusion: stop this Laya efficiency path.** The frozen filter retained every labelled evidence chunk but removed only 4.6% of passage-body bytes. It failed the 50% minimum-reduction gate and the 10-percentage-point advantage gate. Broader coding-agent trials remain paused. The conditional GPT-6 Luna paired trial was skipped; no new Luna run or paid API trial was launched.

Eight information needs used actual project docs and previously captured command/error outputs, without generated padding. Their 25 evidence-span labels mapped to 17 required case/chunk pairs and were written before predictions. The [manifest](offload-screen/manifest.json), [checksum](offload-screen/manifest.sha256), and [runner source](offload-screen/runner-source.py) freeze corpus content, labels, queries, chunking, checkpoint, threshold, baselines, and gate. Source and runner hashes matched at screen completion; the [frozen input archive](offload-screen/frozen-inputs.zip) preserves those exact sources before later checkpoint documentation changes. These are curated known project artifacts, not a fresh held-out corpus or deployment validation.

| Method | Labelled evidence kept | Complete cases | Input bytes removed | Selection time |
| --- | ---: | ---: | ---: | ---: |
| unfiltered | 17/17 | 8/8 | 0.0% | 0.003 s |
| keyword | 15/17 | 6/8 | 46.9% | 0.066 s |
| keyword_context | 16/17 | 7/8 | 26.3% | 0.039 s |
| laya | 17/17 | 8/8 | 4.6% | 377.285 s |

Keyword selection matched normalized query terms. Its context variant also kept one adjacent chunk on each side within the same source event/document. Search was fast and removed more input, but both methods lost required evidence. Keyword-only missed platform requirements and the skill-trigger description; adding context recovered the trigger but still missed the platform requirement. Neither should silently trim this material without an evidence check. Unfiltered input was the only baseline preserving every labelled chunk.

Laya used the already-cached pinned English checkpoint (`20aed815fc6acde75733882e7ec0e3f28aeb9717`) through the existing JSONL batch CLI and resident worker. Each bounded passage was classified keep/discard against its information need, with minimum option probability 0.9. Abstention, invalid output, and unavailability kept the passage; no threshold was lowered or tuned after results. Cold warming took 1.87 seconds, reported separately from filtering. The private worker was stopped after the screen.

Of 1,232 classifications, 995 (80.8%) abstained for low confidence, 232 confidently discarded a passage, and 5 confidently kept one. Of 17 required chunks, 15 survived through abstention fallback and only 2 were confidently selected as relevant. Thus complete recall largely came from retaining uncertain input. There were no truncation or runtime-error responses. Probability thresholds are not calibrated accuracy guarantees.

| Query | Required chunks kept | Bytes removed | Abstentions | CLI filtering time |
| --- | ---: | ---: | ---: | ---: |
| negative_infinity | 1/1 | 4.9% | 186 | 60.01 s |
| permission_boundary | 1/1 | 6.1% | 170 | 66.26 s |
| worker_unavailable | 3/3 | 3.4% | 195 | 87.92 s |
| empty_stdout | 2/2 | 2.1% | 204 | 89.12 s |
| uncertain_answer | 3/3 | 3.1% | 65 | 23.60 s |
| cache_and_idle | 1/1 | 8.4% | 57 | 17.76 s |
| platform_and_provisioning | 3/3 | 9.6% | 60 | 16.86 s |
| prewarm_and_triggers | 3/3 | 5.9% | 58 | 15.77 s |

The corpus contained 409,996 input bytes across queries; Laya retained 390,934. These are UTF-8 passage-body bytes, not provider tokens or billed savings. Query text, provenance framing, and downstream agent overhead are outside that byte count. Baseline time measures in-memory Python selection; Laya time measures actual warmed CLI batches including IPC, inference, and output handling. Common corpus extraction and request-file preparation are outside those timing intervals. No whole-task speed comparison or confidence interval follows from this local screen.

[Full results](offload-screen/results.json) retain per-case selections, missing-evidence IDs, latency, and gate outcomes. Per-case request/response JSONL files retain every prediction, including abstentions. The [decision record](offload-screen/decision.json) records the completed steps and conditional skip. Existing CLI functionality remains experimental; no filtering hook, production filter feature, or automatic decision policy was installed.

Historical reproduction uses `.venv/bin/python benchmarks/offload_screen.py prepare NEW_OUTPUT`, then `run NEW_OUTPUT`. The runner requires the MLX development environment and the cached checkpoint configuration prepared in the earlier pilot (`/tmp/cam-laya-pilot-runtime-path`); it copies that provision into disposable XDG directories and never downloads models. Temporary configurations and the marker have now been archived and removed, so explicit restoration is needed for those historical commands; see the [archive inventory](trial-archives.md). Existing completed output directories are guarded against silent reruns. The archived runner source is for audit; execute from its original `benchmarks/` location.
