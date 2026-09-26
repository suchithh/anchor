# Running grounding score demo

Pitch: Our harness maintains persistent grounding state as selected claims are checked. A post-hoc reviewer checks the collected output at the end.

## Actual implementation

Every successful claim commit updates support, contradiction and insufficient-evidence scores atomically in MongoDB. New commits now also retain their sequence, timestamp and score snapshot. Poll GET /runs/{run_id} while the agent continues; add ?include_events=true for the trace. This is a score over checked claims, not a guarantee about unchecked output.

Run the illustrative replay without any API calls:

```powershell
.\.venv\Scripts\python.exe -m scripts.running_score_demo
```

The replay uses recorded model judgments in input order, not measured original completion order. The post-hoc waiting column illustrates the workflow; it does not measure how long an actual agent spent generating claims.

## Recorded numbers we can defend

MEASURED: one existing completed pass with 36 claims, from technical_http/latest.json, zero-based repetition 1. These are previous measurements, not a new benchmark of the added history fields.

| System path | Accuracy | Complete batch time | Verifier calls |
|---|---:|---:|---:|
| Running verification, fresh | 94.4% MEASURED | 5.00 s MEASURED | 36 MEASURED |
| Running verification, fully reused | 94.4% MEASURED | 2.77 s MEASURED | 0 MEASURED |
| Separate post-hoc reviewer | 100% MEASURED | 10.12 s MEASURED | 1 MEASURED |

- "In this recorded pass, our incremental verification path completed the batch 50.6% sooner than the post-hoc reviewer." MEASURED; accuracy was lower, as shown.
- "On the repeated pass, persistent verified-state reuse avoided all 36 verifier calls and reduced average claim-verification latency by 45.3%." MEASURED; cache reuse retained the original verdicts, including mistakes.
- "The system keeps a grounding score as checks complete, with a persisted score snapshot for each new committed claim." IMPLEMENTED; no claim of measured earlier intervention or improved final agent output.

Other passes had network failures. This comparison is one complete pass, not a reliability average or a universal speedup. Earlier-warning lead time during a real agent run remains UNAVAILABLE. The fresh and reused paths used Jev; the post-hoc reviewer used DeepSeek. The integration verifier remains configurable.
