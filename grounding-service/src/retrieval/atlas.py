import asyncio
from time import perf_counter

from src.models import Chunk, EvidenceBundle
from src.retrieval.fusion import reciprocal_rank_fusion
from src.util import elapsed


def chunk_from_document(doc):
    return Chunk.model_validate({"id": doc["_id"], **{k: v for k, v in doc.items() if k != "_id"}})


class AtlasRetriever:
    def __init__(self, db, embeddings, settings):
        self.db, self.embeddings, self.s = db, embeddings, settings

    async def retrieve_evidence(self, claim, scope, revision, top_k=None):
        start = perf_counter()
        top_k = top_k or self.s.top_k
        rerank = self.s.reranker == "voyage" or self.s.retrieval_mode == "hybrid_reranked"
        limit = max(10, top_k) if rerank else top_k
        vector, emb_usage = await self.embeddings.embed([claim], "query")
        filters = {**scope, "corpus_revision": revision}
        vector_pipeline = [
            {
                "$vectorSearch": {
                    "index": self.s.vector_index_name,
                    "path": "embedding",
                    "queryVector": vector[0],
                    "numCandidates": max(100, limit * 20),
                    "limit": limit,
                    "filter": filters,
                }
            },
            {"$project": {"embedding": 0}},
        ]

        async def aggregate(pipeline):
            return await (await self.db.source_chunks.aggregate(pipeline)).to_list(length=limit)

        if self.s.retrieval_mode != "vector":
            lexical = [
                {
                    "$search": {
                        "index": self.s.search_index_name,
                        "compound": {
                            "must": [{"text": {"path": "text", "query": claim}}],
                            "filter": [{"equals": {"path": k, "value": v}} for k, v in filters.items()],
                        },
                    }
                },
                {"$limit": limit},
                {"$project": {"embedding": 0}},
            ]
            ranks = await asyncio.gather(aggregate(vector_pipeline), aggregate(lexical))
            # Portable RRF deliberately avoids assuming preview native fusion support.
            docs = reciprocal_rank_fusion(ranks, limit)
        else:
            docs = await aggregate(vector_pipeline)
        chunks = [chunk_from_document(d) for d in docs]
        pre_ids = [c.id for c in chunks]
        usage = [emb_usage]
        rerank_ms = 0
        if rerank and chunks:
            rerank_start = perf_counter()
            chunks, u = await self.embeddings.rerank(claim, chunks, top_k)
            usage.append(u)
            rerank_ms = elapsed(rerank_start)
        return EvidenceBundle(
            claim=claim,
            chunks=chunks[:top_k],
            retrieval_latency_ms=elapsed(start),
            retrieval_mode=self.s.retrieval_mode,
            reranker_latency_ms=rerank_ms,
            pre_rerank_ids=pre_ids,
            usage=usage,
        )
