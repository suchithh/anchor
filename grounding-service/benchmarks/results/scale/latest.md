# Grounding benchmark

Status: **stopped_for_integration**

Missing configuration: none

Notes:

- Only completed checkpoints are retained; in-flight calls may have unreturned costs. The scaling experiment is incomplete.

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| atlas_jev / cold (completed) | 50 | 1 | 815.978 | 1662.71 | 5406.46 | 0.00174805 ESTIMATED | 0.00173569 |
| atlas_jev_cached / cold (completed) | 50 | 1 | 1049.13 | 1461.24 | 6300.73 | 0.00162327 ESTIMATED | 0.00161179 |
| atlas_jev_cached / warm (completed) | 50 | 1 | 554.023 | 588.697 | 3276.58 | 0 | 0 |
| atlas_llm_cached / cold (partial_failure) | 50 | 0.97619 | 1711.55 | 2319.37 | 35977.9 | 0.00292479 ESTIMATED | 0.00291331 |
| atlas_llm_cached / warm (partial_failure) | 50 | 0.97619 | 533.7 | 564.148 | 32128.4 | 2.84304e-05 ESTIMATED | 2.81904e-05 |
| atlas_llm_judge / cold (partial_failure) | 50 | 0.97619 | 1405.09 | 3735.4 | 81524 | unavailable | unavailable |
| llm_parallel / cold (partial_failure) | 50 | 0.952381 | 1452.37 | 3285.82 | 36645.4 | 0.00489156 ESTIMATED | 0.0048792 |
| llm_posthoc / cold (completed) | 50 | 1 | 10390.9 | 10391 | 10391.4 | 0.0038535 | 0.0038535 |
| atlas_jev / cold (completed) | 500 | 0.97619 | 882.753 | 1191.18 | 5388.31 | 0.00175645 ESTIMATED | 0.00174409 |
| atlas_jev_cached / cold (partial_failure) | 500 | 0.952381 | 1022.98 | 1361.4 | 34708.7 | 0.00158879 ESTIMATED | 0.00157731 |
| atlas_jev_cached / warm (completed) | 500 | 0.97619 | 517.576 | 545.38 | 3187.96 | 4.1984e-05 ESTIMATED | 4.1664e-05 |
| atlas_llm_judge / cold (partial_failure) | 500 | 0.952381 | 1504.72 | 4458 | 90957.3 | unavailable | unavailable |
| llm_parallel / cold (completed) | 500 | 0.97619 | 1645.76 | 5552.96 | 14335 | 0.00461285 ESTIMATED | 0.00460049 |

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|
| 50 | completed | completed | Atlas+Jev faster; accuracy Jev=1.000, post-hoc=1.000; Atlas+Jev cheaper (ESTIMATED/actual) |
| 500 | unavailable | completed | Not measured |

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.

Run error: Stopped at user request to prioritize merging the upstream claim/context component. No 5000-chunk crossover established.
