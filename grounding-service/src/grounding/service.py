import asyncio
from datetime import datetime, timezone
from time import perf_counter

from src.grounding.cache import cache_key
from src.models import Judgment, VerificationResult
from src.util import digest, elapsed, normalize


class GroundingService:
    def __init__(self, db, retriever, verifier, cache, runs, settings, cache_enabled=True, namespace="live"):
        self.db, self.retriever, self.verifier = db, retriever, verifier
        self.cache, self.runs, self.s = cache, runs, settings
        self.cache_enabled = cache_enabled
        self.policy = digest(
            {
                "verifier": verifier.identity,
                "retrieval": settings.retrieval_mode,
                "top_k": settings.top_k,
                "embedding": settings.voyage_model,
                "dimensions": settings.embedding_dimensions,
                "reranker": settings.reranker,
                "rerank_model": settings.voyage_rerank_model,
                "namespace": namespace,
            }
        )

    async def verify(self, request):
        start = perf_counter()
        lookup_start = perf_counter()
        corpus = await self.db.corpora.find_one({"_id": request.scope["corpus_id"], "status": "ready"})
        if not corpus:
            raise ValueError("Corpus is not ingested and ready")
        if (
            corpus["embedding_model"] != self.s.voyage_model
            or corpus["embedding_dimensions"] != self.s.embedding_dimensions
        ):
            raise ValueError("Query embedding config differs from ingested corpus")
        revision = corpus["revision"]
        provenance = {
            "corpus_id": request.scope["corpus_id"],
            "corpus_revision": revision,
            "policy": self.policy,
            "alpha": self.s.grounding_alpha,
            "order": "verification_commit",
            "importance_weighting": False,
        }
        previous = await self.runs.previous(request, provenance)
        if previous:
            result = VerificationResult.model_validate(previous)
            return result.model_copy(
                update={
                    "deduplicated": True,
                    "usage": [],
                    "verifier_cost": 0,
                    "cache_lookup_latency_ms": elapsed(lookup_start),
                    "retrieval_latency_ms": 0,
                    "reranker_latency_ms": 0,
                    "verifier_latency_ms": 0,
                    "persistence_latency_ms": 0,
                    "total_latency_ms": elapsed(start),
                }
            )
        key = cache_key(request, revision, self.policy)
        cached = await self.cache.get(key, request.scope, revision) if self.cache_enabled else None
        lookup_ms = elapsed(lookup_start)
        bundle = None
        if cached:
            judgment = Judgment.model_validate(cached)
            evidence_ids = cached["evidence_ids"]
            verifier_ms, cost, usages = 0, 0, []
        else:
            query = request.claim + ("\nContext: " + request.context if request.context else "")
            bundle = await self.retriever.retrieve_evidence(query, request.scope, revision)
            tick = perf_counter()
            judgment, u = await self.verifier.judge(request, bundle.chunks)
            verifier_ms, cost = elapsed(tick), u.cost
            usages = [*bundle.usage, u]
            evidence_ids = [c.id for c in bundle.chunks]
        result = VerificationResult(
            **judgment.model_dump(),
            run_id=request.run_id,
            claim_id=request.claim_id,
            evidence_ids=evidence_ids,
            cache_lookup_latency_ms=lookup_ms,
            retrieval_latency_ms=bundle.retrieval_latency_ms if bundle else 0,
            reranker_latency_ms=bundle.reranker_latency_ms if bundle else 0,
            verifier_latency_ms=verifier_ms,
            verifier_cost=cost,
            cache_hit=cached is not None,
            usage=usages,
            corpus_revision=revision,
            verifier=self.verifier.identity,
            avoided_verifier_cost=cached.get("verifier_cost") if cached else None,
            avoided_cost_kind=cached.get("cost_kind", "unavailable") if cached else "unavailable",
        )
        persist_start = perf_counter()
        if self.cache_enabled and not cached:
            await self.cache.put(
                key,
                {
                    **judgment.model_dump(mode="json"),
                    "normalized_claim": normalize(request.claim),
                    "claim_hash": digest(normalize(request.claim)),
                    "context": request.context,
                    "scope": request.scope,
                    "corpus_revision": revision,
                    "policy": self.policy,
                    "evidence_ids": evidence_ids,
                    "source_hashes": [c.content_hash for c in bundle.chunks],
                    "verified_at": datetime.now(timezone.utc),
                    "verifier": self.verifier.identity,
                    "latency_ms": elapsed(start),
                    "verifier_cost": cost,
                    "cost_kind": usages[-1].cost_kind,
                },
            )
        result.total_latency_ms = elapsed(start)
        committed = await self.runs.record(request, result, provenance)
        result.deduplicated = not committed
        if not committed:
            # Another worker won. Return its scored judgment while retaining this attempt's costs/timings.
            winner = await self.runs.previous(request, provenance)
            result = result.model_copy(
                update={
                    **Judgment.model_validate(winner).model_dump(),
                    "evidence_ids": winner["evidence_ids"],
                }
            )
        result.persistence_latency_ms = elapsed(persist_start)
        result.total_latency_ms = elapsed(start)
        return result

    async def verify_batch(self, requests, max_concurrency=None, return_exceptions=False):
        concurrency = self.s.max_concurrency if max_concurrency is None else max_concurrency
        if concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        semaphore = asyncio.Semaphore(concurrency)

        async def one(request):
            async with semaphore:
                return await self.verify(request)

        return await asyncio.gather(*(one(r) for r in requests), return_exceptions=return_exceptions)
