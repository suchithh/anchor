# Grounding benchmark

Status: **interrupted_unbounded_database_operation**

Missing configuration: none

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas_jev / cold (completed) | 582 | 0.944444 | 918.005 | 1470.94 | 4841.61 | 0.00251609 ESTIMATED | 0.00250089 |
| atlas_jev_cached / cold (completed,partial_failure) | 582 | 0.930556 | 1049.59 | 1388.28 | 11039.1 | unavailable ESTIMATED | unavailable |
| atlas_jev_cached / warm (completed) | 582 | 0.944444 | 524.251 | 563.408 | 2674.22 | 3.7295e-05 ESTIMATED | 3.7065e-05 |
| atlas_llm_judge / cold (completed) | 582 | 1 | 1354.17 | 3604.56 | 58406.5 | 0.00145632 ESTIMATED | 0.00144112 |
| llm_parallel / cold (completed) | 582 | 1 | 1517.58 | 3931.57 | 10502.1 | 0.00134992 ESTIMATED | 0.00133472 |
| llm_posthoc / cold (completed) | 582 | 1 | 10190 | 10532.3 | 10192.5 | 0.00206792 | 0.00206792 |

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.

Run error: Third repetition stalled after 35 cold cached claims despite HTTP deadline. MongoDB operation timeout added before subsequent runs; exact stalled stage not recovered.
