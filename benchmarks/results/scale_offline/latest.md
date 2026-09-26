# Grounding benchmark

Status: **offline_dataset_validation_only**

Missing configuration: MONGODB_URI, OPENROUTER_API_KEY, VOYAGE_API_KEY, BASELINE_MODEL

| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |
|---|---:|---:|---:|---:|---:|---:|---:|

No live measurements. Offline dataset validation does not measure model quality, cost, or latency.

| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |
|---:|---|---|---|

No cost/latency winner or crossover can be claimed without completed live measurements.

Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.
API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.
LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.
p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.
Grounding uses completion-order EWMA. The 36-claim PDF sample cannot establish statistical superiority.
