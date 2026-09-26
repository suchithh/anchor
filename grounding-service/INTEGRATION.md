# Verification component handoff

The upstream component owns selecting claims and supplying context. This service owns corpus
retrieval, evidence-support judgments, persistent exact caching, and running grounding scores.
It does not extract claims, assign risk, block agent actions, or rewrite answers.

## Start

Credentials and the `http_rfc` corpus are already configured in this workspace.

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload
```

The integration default is `VERIFIER=llm`, using the configured
`BASELINE_MODEL=deepseek/deepseek-v4.1-flash`. It was more accurate on the technical claims
and sometimes cheaper than Jev. `VERIFIER=jev` selects Jev instead; use a new run ID after
changing the verifier. Both use the same Atlas retrieval, cache and score implementation.
Vector retrieval remains the measured default. Hybrid and reranking are optional experiments.

## Contract to merge against

`POST http://127.0.0.1:8000/verify`

```json
{
  "run_id": "agent-session-001",
  "claim_id": "turn-3-claim-1",
  "claim": "An unqualified no-cache response requires successful validation before reuse.",
  "context": "Reviewing an HTTP cache implementation against RFC 9111.",
  "scope": {"corpus_id": "http_rfc", "source_id": "rfc9111"},
  "importance": 1.0
}
```

- `run_id`: one agent session and fixed corpus/verifier policy. Scores use verification commit order.
- `claim_id`: stable for a retry of the same request. Reusing it with different claim/context/scope
  is a conflict. Give a changed proposition a new ID.
- `claim`: one factual proposition selected upstream.
- `context`: optional disambiguation, **not trusted evidence**. Agent assertions in context cannot
  prove themselves. Tool observations or project files that should count as evidence need to be
  ingested into the source corpus with provenance.
- `scope`: required `corpus_id`; optional exact `source_id` and `version`. Other keys are rejected.
  Supplying known source/version filters avoids some identifier retrieval errors. Ingest the
  actual project corpus before checking claims outside the HTTP demo domain.
- `importance`: finite, nonnegative, default 1. Accepted and preserved; currently does not weight
  the score. Selection/risk remain upstream responsibilities.

Response fields include `run_id`, `claim_id`, `verdict`, `p_supported`, `p_contradicted`,
`p_insufficient`, `probability_kind`, `evidence_ids`, `corpus_revision`, `verifier`, `cache_hit`,
`deduplicated`, `usage`, and separate timing fields. DeepSeek returns a label represented as a
one-hot vector (`probability_kind=one_hot_label`), **not calibrated confidence**. Jev returns a
model distribution, which is also not guaranteed to be calibrated.

`POST /verify/batch` accepts `{"requests": [<same request objects>], "max_concurrency": 8}` and
returns a result or explicit error per claim. `GET /runs/{run_id}` returns the three EWMAs,
claim/cache counts and provenance. First result initializes the scores; later updates use alpha 0.8.
For a live score trace, use `GET /runs/{run_id}?include_events=true`. Newly committed events contain
`commit_sequence`, `committed_at`, and `score_after` with all three scores. Sort by `commit_sequence`;
each snapshot is recorded atomically with the judgment and running score. Older events do not have
these added fields. Poll the normal endpoint for the current score without downloading history.

For a zero-API demonstration, run `python -m scripts.running_score_demo`. It replays saved judgments
in input order and displays the evolving score beside a post-hoc reviewer waiting for the batch.
This is explicitly an illustrative replay, not measured original event timing or a new benchmark.

## Keep verification off the agent's critical path

The HTTP request waits for its result. The **caller schedules it in the background**:

```python
import asyncio
import httpx

async def verify(client, selected_claim):
    response = await client.post('/verify', json=selected_claim)
    response.raise_for_status()
    return response.json()

async def run_with_verification(selected_claims):
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=180) as client:
        pending = [asyncio.create_task(verify(client, claim)) for claim in selected_claims]
        # Continue the main agent here; retain tasks and keep the client alive.
        results = await asyncio.gather(*pending, return_exceptions=True)
        return results
```

For a continuing stream, submit each selected claim as it arrives and retain its task until
completion. Bound upstream outstanding work; use `/verify/batch` for batches. There is no durable
background queue, so pending tasks do not survive a process crash. Completed results do persist.

HTTP 409 means conflicting IDs or changed run provenance; 422 means invalid input/configuration;
502 means verification failed. A batch can return HTTP 200 with per-claim errors. Keep failed or
pending checks separate from `INSUFFICIENT`: a network error is not an evidence judgment. Retry
the same unchanged request with the same IDs when appropriate; successful commits count once.
Provider requests have a 90-second deadline; each database operation has a 30-second deadline.

## What the experiments support

The five official HTTP RFCs provide 582 technical chunks and 36 audited claims. Jev repeatedly
classified 34/36 correctly; successful DeepSeek judgments were more accurate. Jev incorrectly
supported an arithmetic claim with 0.91 support probability, so confidence must not become an
automatic action-safety threshold. Cache reuse preserves both correct and incorrect judgments.

Healthy warm batches of 36 claims took about 2.7 seconds with roughly 0.53-second median service
latency and zero model calls. This is a harness benefit available to either verifier, not a Jev-only
advantage. An atomic MongoDB score update removed the earlier cache contention.

At 500 synthetic chunks, vector-only retrieval omitted an exact package/version document and
both judges missed the same claim. Hybrid retrieval is implemented but its proposed follow-up
experiment was stopped for the integration handoff. No 5,000-chunk crossover is established.

Live network timeouts affected some batches. Raw reports retain these failures. One older post-hoc
run discarded a batch after a persistence failure; that reporting behavior is fixed and unit-tested,
but its live rerun was intentionally stopped. Do not present that row as model factual accuracy.
