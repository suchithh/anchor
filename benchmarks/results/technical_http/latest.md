# Grounding benchmark

Status: **completed_with_failures**

Missing configuration: none

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas_jev / cold (completed) | 582 | 0.944444 | 915.934 | 1846.82 | 5055.74 | 0.00251862 ESTIMATED | 0.00250342 |
| atlas_jev_cached / cold (completed,partial_failure) | 582 | 0.916667 | 1127.06 | 1386.86 | 24931.8 | unavailable ESTIMATED | unavailable |
| atlas_jev_cached / warm (completed) | 582 | 0.944444 | 540.737 | 762.091 | 2791.09 | 5.10767e-05 ESTIMATED | 5.089e-05 |
| atlas_llm_judge / cold (completed,partial_failure) | 582 | 0.990741 | 1318.24 | 3654.57 | 72031.4 | 0.00140692 ESTIMATED | 0.00139172 |
| llm_parallel / cold (completed,partial_failure) | 582 | 0.990741 | 1481.12 | 3510.6 | 38517.8 | unavailable ESTIMATED | 0.00127737 |
| llm_posthoc / cold (completed,failed) | 582 | 0.666667 | 10876.7 | 11639.6 | 21597.9 | 0.00206792 | 0.00206792 |

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.
