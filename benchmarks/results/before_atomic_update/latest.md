# Grounding benchmark

Status: **completed**

Missing configuration: none

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas_jev / cold (completed) | 582 | 0.944444 | 1072.87 | 2702.76 | 6542 | 0.0025184 ESTIMATED | 0.0025032 |
| atlas_jev_cached / cold (completed) | 582 | 0.944444 | 1274.52 | 2026.92 | 6720.23 | 0.0025184 ESTIMATED | 0.0025032 |
| atlas_jev_cached / warm (completed) | 582 | 0.944444 | 1429.53 | 1870.78 | 6979.53 | 0 | 0 |
| atlas_llm_judge / cold (completed) | 582 | 1 | 1415.49 | 3783.11 | 62017.2 | 0.00154134 ESTIMATED | 0.00152614 |
| llm_parallel / cold (completed) | 582 | 1 | 1587.21 | 3904.97 | 10056.5 | 0.00247777 ESTIMATED | 0.00246257 |
| llm_posthoc / cold (completed) | 582 | 1 | 15832.1 | 16077.1 | 15649.3 | 0.0601349 | 0.0601349 |

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.
