# Grounding benchmark

Status: **running**

Missing configuration: none

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas_jev / cold (completed) | 582 | 0.944444 | 857.513 | 2429.94 | 5610.47 | 0.00251643 ESTIMATED | 0.00250123 |
| atlas_jev_cached / cold (partial_failure) | 582 | 0.916667 | 1049.19 | 1324.39 | 34744.3 | 0.00251643 ESTIMATED | 0.00250123 |
| atlas_jev_cached / warm (completed) | 582 | 0.944444 | 540.737 | 564.356 | 2689.61 | 0 | 0 |
| atlas_llm_judge / cold (completed) | 582 | 1 | 1307.88 | 3586.96 | 55126.3 | 0.0012508 ESTIMATED | 0.0012356 |
| llm_parallel / cold (partial_failure) | 582 | 0.972222 | 1428.73 | 3540.78 | 96209.1 | unavailable | 0.00133377 |
| llm_posthoc / cold (completed) | 582 | 1 | 11639.6 | 11639.6 | 11643.4 | 0.00206792 | 0.00206792 |

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.
