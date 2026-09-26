# Running grounding harness

**Integration handoff:** see [INTEGRATION.md](INTEGRATION.md) for the exact upstream contract,
background-calling example, failure semantics and measured design decisions. Benchmark expansion
was stopped to prioritize merging the claim/context supplier. The HTTP service now defaults to
DeepSeek (`VERIFIER=llm`); Jev remains selectable with `VERIFIER=jev`.

Verify selected claims against a declared corpus, persist reusable evidence judgments in MongoDB,
and maintain support / contradiction / insufficient-evidence EWMAs. This implements the verification
component only. Claim selection, risk inference, output correction, and a frontend are outside its scope.

The code and offline tests are implemented. Atlas connectivity and small Voyage/Jev/DeepSeek calls
have passed live checks. Benchmark reports include completed passes, network failures and intentionally
unfinished scaling experiments; consult their status before using any result. The current primary baseline is `deepseek/deepseek-v4.1-flash`, with reasoning disabled
and bounded structured output. Catalog prices are starting prices; actual routed usage costs prevail.

The primary suite is now **technical_http**: five official RFC snapshots, 582 section-aware chunks,
and 36 manually audited claims. It tests caching directive qualifications, precedence, overflow,
entity-tag comparisons, HTTP message framing, and absent deployment/runtime information. RFC editions,
URLs, hashes and original licensing notices are retained in `benchmarks/datasets/http_rfc/`.
The PDF remains a smoke test and source of hackathon requirements; the synthetic suite controls scaling.

## Hackathon requirements verified

The authoritative local resource guide is
`_5BEXTERNAL_5D_20THE_20HARNESS_20ENGINEERING_20&_20MODEL_20WRANGLING_20HACKATHON.pdf`.
Printed page numbers match PDF page numbers:

| Requirement | PDF page | Finding |
|---|---:|---|
| MongoDB data and memory layer | 2 | Explicit |
| Finalists use Atlas Hackathon Sandbox | 3 | Explicit; create project/cluster through emailed link |
| Vector Search and Atlas Search | 4 | Both listed; sandbox Vector Search index creation verified live |
| OpenRouter credits | 6 | Provided to checked-in participants; amount/expiry unspecified |
| Voyage AI allowance | 7–8 | 200 million free tokens per participant; API key must be created |

The guide also requires original work, a public repository, an accessible demo, and at most four team
members. This folder initially contained only the PDF, with no Git repository or application scaffold.
No undocumented cluster tier, model entitlement, database region, native fusion version, or hosted
worker service is assumed. Automated Embeddings being listed does not establish sandbox enablement.

## Setup

Python 3.11+ is recommended. The implementation also runs on the machine's installed Python 3.10.8.
PowerShell, from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
Copy-Item .env.example .env
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe` in place of `python`, and
`python -m uvicorn` in place of `uvicorn`. A ready-to-use `.venv` was created during implementation.
For reproducible versions on this Windows/Python 3.10 environment, `requirements-tested.txt` records
the tested dependency set; use `python -m pip install -r requirements-tested.txt` before installing
the editable project. Other Python/platform combinations may need a fresh dependency resolution.

Edit `.env` locally (ignored by Git):

```dotenv
MONGODB_URI=mongodb+srv://<database-user>:<password>@<sandbox-cluster>/
MONGODB_DB=grounding_harness
OPENROUTER_API_KEY=<your-key>
VOYAGE_API_KEY=<your-key>
BASELINE_MODEL=<OpenRouter model ID supporting strict structured outputs>
```

Use the **emailed Atlas Hackathon Sandbox** cluster, configure its database user and network access,
and grant collection/index creation privileges. The program cannot infer whether your Atlas project
belongs to the event sandbox. Choose a baseline model you want to compare; there is no hidden model
default. This workspace uses `deepseek/deepseek-v4.1-flash`; Jev defaults to `typesafe/jev-1.13`.
The MongoDB plugin provisioned a database user scoped to this application database. Credentials
are saved only in the ignored `.env`; do not publish that file.
The live benchmark accepts standard Atlas `*.mongodb.net` connection hosts and rejects local MongoDB.

## Run

```powershell
# Audited PDF fixture regeneration; review labels if the PDF changes.
python -m benchmarks.generate_pdf_dataset

# Ingestion automatically creates indexes, embeds chunks, and waits for searchable data.
python -m scripts.ingest_pdf
# Or specify the PDF explicitly:
python -m scripts.ingest_pdf '.\_5BEXTERNAL_5D_20THE_20HARNESS_20ENGINEERING_20&_20MODEL_20WRANGLING_20HACKATHON.pdf'

# Optional separate index setup/status check:
python -m scripts.setup_atlas

# These commands use live Atlas + paid/credited provider APIs.
python -m benchmarks.run --suite technical_http --repetitions 3
python -m benchmarks.run --suite hackathon_pdf --repetitions 3
python -m benchmarks.run --suite scale --sizes 50 500 5000 --repetitions 3

# Separate output directories preserve comparisons.
python -m benchmarks.run --suite hackathon_pdf --retrieval-mode hybrid --output benchmarks/results/hybrid
python -m benchmarks.run --suite hackathon_pdf --reranker voyage --output benchmarks/results/reranked

# No external services; validate fixtures, never invent benchmark results.
python -m benchmarks.run --suite scale --sizes 50 500 5000 --offline --output benchmarks/results/scale_offline
python -m benchmarks.run --suite technical_http --offline --output benchmarks/results/technical_offline
python -m pytest -q
python -m ruff check .

python -m uvicorn src.api.main:app --reload
```

Every benchmark command writes `latest.json`, `latest.csv`, and `latest.md` in its output directory.
The CLI defaults to the technical HTTP suite. To re-download its source snapshots, run
`python -m scripts.fetch_technical_corpus`, then review and regenerate labels with
`python -m benchmarks.generate_technical_dataset`.
Raw JSON is also archived by benchmark ID under `results/runs/`. A missing configuration yields a
blocked report and exit code 2. Offline dataset validation exits 0. Other failures exit 1 and preserve
their status. Default output is exactly `benchmarks/results/latest.{json,csv,md}`.

Ingestion is resumable: deterministic IDs avoid re-embedding existing chunks for the same revision.
It never deletes older revisions or unrelated data. Corpus ID + revision are search prefilters.
New revisions become active only after the actual expected chunk count can be retrieved, not just
after an index reports READY. Index permission, build, or query errors are surfaced; no fallback to
local vectors occurs. Index readiness has a 180-second timeout; rerun ingestion after resolving it.
Ingestion supports up to 5,000 chunks, matching the requested experiments.

## Integration API

`POST /verify` accepts:

```json
{
  "run_id": "agent-session-1",
  "claim_id": "claim-1",
  "claim": "Finalist projects must use the MongoDB Atlas Hackathon Sandbox.",
  "context": null,
  "scope": {"corpus_id": "hackathon_pdf"},
  "importance": 1.0
}
```

`scope.corpus_id` is mandatory. Optional exact string filters are `source_id` and `version`.
Unknown filters and MongoDB operators are rejected rather than ignored. `importance` is accepted
and preserved in request identity but deliberately not used in the score in this MVP.

`POST /verify/batch` takes `{"requests": [...], "max_concurrency": 8}` and returns a result or an error
per claim. The server caps this value at `MAX_CONCURRENCY`. `GET /runs/{run_id}` returns the running
scores, counts, timestamp and provenance. OpenAPI is available at `/docs`.

Verification returns the verdict, three scores, evidence IDs, corpus revision, verifier identity,
cache status, call usage, and separate lookup/retrieval/verifier/persistence/total timings.
The total measures service execution; the batch wall clock also includes semaphore queueing.
Retrieval time includes embedding and optional reranking; reranker time is additionally broken out.

These HTTP calls await completion. To keep a main agent moving, schedule them as `asyncio` tasks
from the harness or run the batch concurrently with the agent. This is not a durable job queue:
pending tasks do not survive a process crash. Completed state does persist. Local development binds
to localhost; authentication/multi-tenant access control must be added before exposing the API.

## Architecture choices and pushback

1. **Evidence support is not truth or risk.** Retrieval failure can produce INSUFFICIENT even when
   supporting text exists elsewhere. We measure evidence retrieval hit rate separately from verdict
   quality. Scores cover the upstream-selected claims, not every statement the agent makes.
2. **A probability is not proven calibration.** Jev distributions are retained and scored with a
   multiclass Brier score. The LLM returns strict labels; one-hot vectors drive its EWMA but are
   explicitly tagged `one_hot_label` and excluded from probabilistic Brier reporting. Neither score
   establishes the probability that an agent is safe or correct.
3. **Exact caching needs more than claim text.** Cache identity includes whitespace-normalized,
   case-sensitive claim text, exact context, scope, corpus revision, verifier/prompt identity,
   embedding/retrieval/reranker settings, and namespace. Punctuation and case are preserved for
   identifiers. There is no semantic cache. Paraphrases are verified afresh.
4. **Checking cited hashes alone is insufficient.** New or deleted corpus material can change a
   previous INSUFFICIENT verdict. Immutable corpus revision IDs invalidate all prior judgments;
   cached evidence hashes are also checked on each hit. Use ingestion for source changes. Direct
   mutation of immutable corpus documents is unsupported. Older revisions remain for provenance.
5. **Asynchrony makes ordering a design choice.** The request has no turn sequence. EWMAs use
   verification-commit order, so network completion order affects the score. First observation
   initializes all three quantities; subsequent observations use alpha=0.8. This avoids an invented
   optimistic/zero prior and keeps the scores summing to one. A run cannot mix corpus revisions or
   verifier/scoring policies; start a new run when these change.
6. **Persistence must resist duplicate calls and races.** A MongoDB atomic update pipeline computes
   the EWMA and records claim-ID deduplication in the same document. This replaced a client-side
   compare-and-swap loop after live measurements exposed contention during warm cache batches.
   Identical claim IDs count once; reusing an
   ID for different input yields a conflict. Concurrent duplicates may still spend duplicate API
   calls; no distributed single-flight lock is claimed. Runs are capped at 2,000 distinct claims to
   keep the document bounded. Move events to a transaction-backed collection before production
   long-horizon deployment. Completed event timings are snapshots taken before the final write;
   returned/benchmark timings include that write.
7. **The proposed LLM baselines overlap.** `atlas_llm_judge` is the serial control; `llm_parallel`
   is precisely the same retrieval/judge pipeline at configured concurrency. It approximates review
   subagents without inventing orchestration overhead. Equal-concurrency Atlas+LLM and parallel
   reviewer architectures are identical in this MVP.

Collections: `source_chunks`, `verified_claims`, `grounding_runs`, plus a `corpora` active-revision
registry. Claim embeddings are intentionally omitted from `verified_claims`: exact lookup needs
no embedding, and semantic equivalence is out of scope. Evidence embeddings live in `source_chunks`.

## Benchmark interpretation

The PDF suite contains **36 manually audited claims: 12 per label**, with source hash, page numbers,
supporting/contradicting excerpts, and absence notes. Fixture generation validates excerpts; it does
not manufacture labels with a model. Updating the PDF invalidates the recorded source hash and
requires another label audit.

The scale suite generates exactly 50/500/5,000 deterministic versioned technical chunks and
42 claims per size (14 per label), including exact repeats and paraphrases. Templates encode an
independent fact dictionary used by the test oracle. Distractors are the other packages/versions.
This is a controlled stress test, not representative evidence of real-world factuality.

Each repetition shuffles approach order with a recorded seed. All retrieval-based judges receive
**identical evidence per claim within that repetition**. Every approach still performs and pays for
live retrieval; the first evidence result is pinned to control approximate-search variability.
Raw versus judged evidence IDs and pre-rerank IDs are retained. Main latency numbers are measured
wall times, not sums of separately timed components. Pinning is benchmark-only; normal API
requests use their actual retrieval results. Scope and corpus revision are part of the pin key.

| Approach | Execution | Verified-cache behavior |
|---|---|---|
| `llm_posthoc` | One LLM call over all claims and the entire scoped corpus | Disabled |
| `llm_parallel` | Atlas retrieval + LLM, bounded concurrent claims | Disabled |
| `atlas_llm_judge` | Same judge and evidence, serial control | Disabled |
| `atlas_jev` | Atlas retrieval + Jev, bounded concurrent claims | Disabled |
| `atlas_jev_cached` cold/warm | Same Jev path; second pass reuses exact judgments | Isolated per repetition |
| `atlas_llm_cached` cold/warm | Same persistent cache with the DeepSeek judge | Isolated per repetition |

Warm passes use fresh run/claim processing and pay real MongoDB lookup/persistence costs. Both cold
and warm passes are shown. A cold synthetic pass can already hit exact repeats, so its observed hit
rate is reported. Estimated avoided verifier cost is based on the original charged call and is a
counterfactual estimate, never claimed as a newly measured bill reduction.
The extra cached-LLM control prevents attributing a general caching benefit specifically to Jev.
Use `--approaches atlas_llm_cached` to run that control alone; selection is recorded in the report.

For post-hoc, the default `POSTHOC_MAX_INPUT_BYTES=60000` is an explicit conservative UTF-8 payload
guard, **not a token-count estimate or a discovered model context limit**. Set it to an appropriate
budget for your selected model to test larger full-context calls. Oversized payloads are marked
`skipped_context_budget`, never truncated or counted as losses. A skipped row does not demonstrate
a crossover. All post-hoc claims share the full call/availability latency, rather than dividing one
call's latency by claim count. The optional `jev_full_context` experiment is not implemented.
This workspace sets the guard to **3,000,000 bytes** for DeepSeek's large context, so the full RFC
corpus and synthetic scaling corpus can compete without the default small-payload restriction.

A standalone full-context sanity check (`python -m scripts.check_technical_posthoc`) classified
36/36 HTTP claims correctly using DeepSeek V4.1 Flash: 27.108 seconds, 197,689 input tokens,
704 output tokens, and $0.01609672 actual OpenRouter cost. Its raw artifact is
`benchmarks/results/technical_posthoc_reference.json`. This single call excludes Atlas access
and persistence, so its latency is not an end-to-end architecture comparison.

JSON includes accuracy, macro F1, per-class precision/recall, a confusion matrix with an ERROR column,
Brier score where available, coverage, timing percentiles, batch throughput, API/token/cost counts,
cache savings, and overlap ratios. Failures count against accuracy and recall; failed timings/costs
are not silently labeled as successful INSUFFICIENT judgments. Failed API attempts remain counted,
and an unreturned cost stays unknown. Provider API requests are not retried automatically.
`HTTP_TIMEOUT_SECONDS` bounds the complete provider request as well as HTTP read inactivity.
`MONGODB_TIMEOUT_MS=30000` bounds each database operation, including pool waits and network I/O;
server selection alone does not bound an established connection's operations. The local workload
uses eight concurrent claims and normally subsecond database operations, so 30 seconds leaves
headroom for ingestion and network variation. Monitor per-stage latency and timeout counts before
changing this budget; Atlas connection metrics distinguish pool pressure from network problems.
Interrupted diagnostic runs remain under `technical_pilot` and `before_database_deadline` in
the results directory. Their precise stalled stage could not be recovered, so they are not
evidence of a particular provider's model latency. Final comparisons use both deadlines.

OpenRouter `usage.cost` is recorded when returned. Voyage costs are unknown unless you set explicit
`VOYAGE_USD_PER_MILLION_TOKENS` / `VOYAGE_RERANK_USD_PER_MILLION_TOKENS`; these are labeled ESTIMATED.
Provider token totals are separate. Known cost subtotals do not substitute for unknown total cost.
For the live comparison, this workspace explicitly sets both Voyage rates to $0.02 per million
tokens for `voyage-3.5-lite` and `rerank-2.5-lite`, following the
[Voyage price table](https://docs.voyageai.com/docs/pricing) checked September 26, 2026.
These are list-price estimates, not observed account charges or assumptions about remaining credits.
Atlas hosting is excluded from API cost; ingestion is separately itemized and excluded from steady
state query cost. Free allowances are not treated as zero unit prices.

The Markdown/CSV table aggregates repetitions, with pooled per-claim latency percentiles and mean
batch wall time/cost. The scale table reports latency, cost and accuracy tradeoffs at measured sizes;
it does not extrapolate a threshold. Three repetitions and this small dataset cannot establish
statistical superiority; use more repetitions and representative data before broader claims.

## Optional retrieval experiments

Default is vector-only top 3, no reranker. `RETRIEVAL_MODE=hybrid` creates a lexical index and fuses
vector/text rankings with portable application RRF. Setup inspects the actual cluster's index
definitions and readiness; it does not assume native `$rankFusion` support from a version string.
Native fusion is deliberately deferred until the actual sandbox can be inspected.

`--reranker voyage` retrieves 10 candidates, reranks with Voyage, and keeps 3.
`hybrid_reranked` combines hybrid retrieval with that reranker. Compare the separate output reports:
accuracy, raw/judged evidence hit rate, pre-rerank hit rate, reranker latency and Voyage cost.
No recommendation to enable reranking is justified until live results show a material benefit.

Automated Embeddings is not enabled by this implementation. If the sandbox supports it, follow
[MongoDB's Automated Embedding guide](https://www.mongodb.com/docs/vector-search/crud-embeddings/automated-embedding/):
create a separate `autoEmbed` index on text, use a supported Voyage model, and replace manual query
vectors with the text query supported by that index. This requires a new retriever/ingestion adapter,
not just flipping an environment variable. Keep explicit corpus filters, revision invalidation,
index readiness checks and provider accounting when switching. Its Atlas billing/entitlements must
be measured independently; the PDF does not prove that the event's direct Voyage tokens apply to it.

## Research and API references checked

- [Li & Flanigan, RAC (Findings of EMNLP 2025)](https://aclanthology.org/2025.findings-emnlp.1370/)
  motivates retrieval-assisted factuality correction; this project implements persistent verification,
  not RAC correction/revision, and does not claim RAC's experimental results apply to Jev.
- [OpenRouter Jev overview](https://openrouter.ai/docs/guides/community/jev)
  and [Decisions request/response schema](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request).
- [OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).
- [PyMongo async index management](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/indexes/).
- [Voyage embeddings](https://docs.voyageai.com/reference/embeddings-api)
  and [Voyage reranking](https://docs.voyageai.com/reference/reranker-api).

Mock HTTP contract tests use the documented payloads; live preflight checks separately establish
account/model access. Direct Voyage free-tier limits can prevent embedding batches even when
Atlas billing is configured. Voyage billing belongs to the organization that issued the API key;
allow its stated propagation interval before retrying a rate-limited ingestion.
