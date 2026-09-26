import random
from time import perf_counter

from benchmarks.metrics import metrics
from src.models import VerificationRequest, VerificationResult
from src.retrieval.atlas import chunk_from_document
from src.util import digest, elapsed
from src.verification.llm import ContextBudgetExceeded

APPROACHES = [
    "llm_posthoc",
    "llm_parallel",
    "atlas_llm_judge",
    "atlas_jev",
    "atlas_jev_cached",
    "atlas_llm_cached",
]


class PairedRetriever:
    """Pay for live retrieval on every request, pin evidence across judges within a repetition.

    This controls ANN variability without pretending a precomputed retrieval has zero cost.
    Raw retrieval IDs are retained so pinning changes remain visible.
    """

    def __init__(self, live, pinned):
        self.live, self.pinned = live, pinned
        self.observed = {}

    async def retrieve_evidence(self, claim, scope, revision, top_k=None):
        result = await self.live.retrieve_evidence(claim, scope, revision, top_k)
        key = digest([claim, scope, revision])
        pinned = self.pinned.setdefault(key, result.chunks)
        self.observed[claim] = {
            "raw_ids": [c.id for c in result.chunks],
            "judged_ids": [c.id for c in pinned],
            "pre_rerank_ids": result.pre_rerank_ids,
        }
        return result.model_copy(update={"chunks": pinned})


async def posthoc(rt, requests, revision):
    start = perf_counter()
    docs = (
        await rt.db.source_chunks.find({**requests[0].scope, "corpus_revision": revision}, {"embedding": 0})
        .sort(
            [
                ("source_id", 1),
                ("version", 1),
                ("page", 1),
                ("metadata.section_start_line", 1),
                ("metadata.part", 1),
                ("original_id", 1),
            ]
        )
        .to_list()
    )
    chunks = [chunk_from_document(d) for d in docs]
    retrieval_ms = elapsed(start)
    tick = perf_counter()
    judgments, usage = await rt.llm.posthoc(requests, chunks)
    verifier_ms = elapsed(tick)
    results = []
    provenance = {
        "scope": requests[0].scope,
        "corpus_revision": revision,
        "policy": rt.llm.identity + ":full-context",
        "alpha": rt.s.grounding_alpha,
        "order": "input_order_after_posthoc",
        "importance_weighting": False,
    }
    for i, request in enumerate(requests):
        result = VerificationResult(
            **judgments[request.claim_id].model_dump(),
            run_id=request.run_id,
            claim_id=request.claim_id,
            evidence_ids=[c.id for c in chunks],
            corpus_revision=revision,
            verifier=rt.llm.identity,
            retrieval_latency_ms=retrieval_ms,
            verifier_latency_ms=verifier_ms,
            verifier_cost=usage.cost if i == 0 else 0,
            usage=[usage] if i == 0 else [],
        )
        tick = perf_counter()
        try:
            await rt.runs.record(request, result, provenance)
            result.persistence_latency_ms = elapsed(tick)
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - retain failures per claim, like the parallel baseline
            results.append(exc)
    # All claims become available together. Shared call duration is never divided by N.
    for result in results:
        if isinstance(result, VerificationResult):
            result.total_latency_ms = elapsed(start)
    return results


def evidence_hits(fixtures, records, documents):
    by_id = {d["_id"]: d for d in documents}
    eligible, hits, raw_hits, pre_hits = 0, 0, 0, 0
    for fixture, record in zip(fixtures, records):
        if fixture["gold_label"] == "INSUFFICIENT":
            continue
        eligible += 1

        def match(ids, fixture=fixture):
            for key in ids:
                doc = by_id.get(key, {})
                if fixture.get("gold_original_ids"):
                    if doc.get("original_id") in fixture["gold_original_ids"]:
                        return True
                elif doc.get("page") in fixture["gold_pages"]:
                    # Page-only is too permissive: require the audited quote in the chunk.
                    from src.util import normalize

                    if normalize(fixture.get("gold_quote", "")) in normalize(doc.get("text", "")):
                        return True
            return False

        hits += int(match(record.get("result", {}).get("evidence_ids", [])))
        raw_hits += int(match(record.get("retrieval", {}).get("raw_ids", [])))
        pre_hits += int(match(record.get("retrieval", {}).get("pre_rerank_ids", [])))
    return {
        "eligible_claims": eligible,
        "judged_evidence_hit_rate": hits / eligible if eligible else None,
        "raw_retrieval_hit_rate": raw_hits / eligible if eligible else None,
        "pre_rerank_hit_rate": pre_hits / eligible if eligible else None,
    }


async def run_dataset(rt, fixtures, corpus, repetitions, seed, benchmark_id, on_row=None, approaches=None):
    rows = []
    documents = await rt.db.source_chunks.find(
        {"corpus_id": corpus["corpus_id"], "corpus_revision": corpus["revision"]}, {"embedding": 0}
    ).to_list()
    for repetition in range(repetitions):
        pinned = {}
        order = (approaches or APPROACHES).copy()
        random.Random(seed + repetition).shuffle(order)
        for approach in order:
            passes = ["cold", "warm"] if approach.endswith("_cached") else ["cold"]
            namespace = f"{benchmark_id}:{corpus['corpus_id']}:{repetition}:{approach}"
            for phase in passes:
                run_id = f"{namespace}:{phase}"
                requests = [
                    VerificationRequest(
                        run_id=run_id,
                        claim_id=f["claim_id"],
                        claim=f["claim"],
                        context=f.get("context"),
                        scope=f["scope"],
                    )
                    for f in fixtures
                ]
                paired = PairedRetriever(rt.retriever, pinned)
                service = rt.service(
                    "jev" if "jev" in approach else "llm",
                    cache=approach.endswith("_cached"),
                    namespace=namespace,
                    retriever=paired,
                )
                concurrency = 1 if approach == "atlas_llm_judge" else rt.s.max_concurrency
                marker = len(getattr(rt.http, "grounding_calls", []))
                start = perf_counter()
                status, reason = "completed", None
                try:
                    if approach == "llm_posthoc":
                        output = await posthoc(rt, requests, corpus["revision"])
                    else:
                        output = await service.verify_batch(requests, concurrency, return_exceptions=True)
                except ContextBudgetExceeded as exc:
                    status, reason, output = "skipped_context_budget", str(exc), []
                except Exception as exc:  # noqa: BLE001 - retain failures as benchmark observations
                    status, reason, output = "failed", type(exc).__name__, []
                batch_ms = elapsed(start)
                calls = getattr(rt.http, "grounding_calls", [])[marker:]
                records = []
                for index, request in enumerate(requests):
                    item = output[index] if index < len(output) else None
                    record = {"claim_id": request.claim_id}
                    if isinstance(item, VerificationResult):
                        record["result"] = item.model_dump(mode="json")
                    else:
                        record["error"] = type(item).__name__ if item is not None else reason
                    record["retrieval"] = paired.observed.get(request.claim, {})
                    records.append(record)
                if any("error" in r for r in records) and status == "completed":
                    status = "partial_failure"
                row = {
                    "suite": corpus["corpus_id"],
                    "corpus_size": corpus["num_chunks"],
                    "revision": corpus["revision"],
                    "approach": approach,
                    "phase": phase,
                    "repetition": repetition,
                    "concurrency": concurrency if approach != "llm_posthoc" else 1,
                    "status": status,
                    "reason": reason,
                    "records": records,
                    "calls": calls,
                    "metrics": metrics(fixtures, records, batch_ms, calls, rt.s, approach == "llm_posthoc")
                    if status != "skipped_context_budget"
                    else None,
                    "evidence": evidence_hits(fixtures, records, documents)
                    if approach != "llm_posthoc"
                    else None,
                }
                rows.append(row)
                if on_row is not None:
                    on_row(row)
                print(f"{corpus['corpus_id']} rep={repetition + 1} {approach}/{phase}: {status}", flush=True)
    return rows
