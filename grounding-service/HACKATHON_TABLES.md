# Claim-verification component: existing-results summary

No new benchmark was run. MEASURED: the same 36 audited HTTP RFC claims and identical evidence, using the last existing repetition in which all four required paths completed. This reuses the existing technical corpus; no PDF microbenchmark was necessary.

Latency is mean / p50 per claim, including retrieval or cache lookup, verification, and persistent grounding-state updates. Cost is for the full batch: returned verifier charges plus estimated embedding cost; Atlas hosting is excluded.

| Approach | Accuracy | Latency | Verifier calls | Cost |
|---|---:|---:|---:|---:|
| Fresh verification | 94.4% MEASURED | 934 / 880 ms MEASURED | 36 MEASURED | $0.002523 SMALL-SAMPLE ESTIMATE |
| Reused verification | 94.4% MEASURED | 596 / 545 ms MEASURED | 2 MEASURED | $0.000153 SMALL-SAMPLE ESTIMATE |
| Small LLM reviewer | 100.0% MEASURED | 1671 / 1404 ms MEASURED | 36 MEASURED | $0.001257 SMALL-SAMPLE ESTIMATE |

- Fresh vs reviewer: 44.1% lower mean latency (MEASURED), but 94.4% versus 100% accuracy (MEASURED) and 2.01x the cost (SMALL-SAMPLE ESTIMATE).
- Reused vs fresh: 36.2% lower mean latency, with 34/36 cache hits and 34 verifier calls avoided (MEASURED). Accuracy remained 94.4% (MEASURED). The two cache misses were checked afresh.
- Sequential vs parallel: 66.07 s versus 10.43 s, a 84.2% wall-time reduction at concurrency 8 (MEASURED). This compares the same reviewer-based verification pipeline. Jev-specific sequential wall time: UNAVAILABLE.

Demo claims:

1. "On this sample, reusing persistent verified state reduced average repeat-verification latency by 36.2% and avoided 34 of 36 verifier calls." (MEASURED)
2. "Running the same reviewer-based verification pipeline concurrently reduced batch wall time by 84.2% versus sequential execution on this sample." (MEASURED)

These are one complete-pass comparisons, not reliability averages or general performance guarantees. Other recorded passes had network failures. Cache reuse preserves verdict errors as well as correct judgments.

Source: `benchmarks/results/technical_http/latest.json`, zero-based repetition `2`. Selection was based on all required paths completing, not on fastest latency.
