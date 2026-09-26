# Grounding benchmark

Status: **interrupted_provider_stall**

Missing configuration: none

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas_jev / cold (completed) | 582 | 0.944444 | 1269.65 | 2801.72 | 7468.42 | unavailable | 0.00250123 |

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.

Run error: Three concurrent LLM calls remained open for several minutes; pilot stopped to add an overall request deadline. In-flight costs unavailable.
