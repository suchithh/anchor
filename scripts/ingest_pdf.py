import argparse
import asyncio
import json
from datetime import datetime, timezone
from time import monotonic

from pymongo import UpdateOne

from scripts.setup_atlas import setup
from src.config import Settings
from src.ingestion import find_pdf, parse_pdf
from src.runtime import runtime
from src.util import digest


async def wait_searchable(rt, corpus_id, revision, expected, timeout=180):
    """Check actual retrieval coverage, not merely index READY (eventually consistent)."""
    scope = {"corpus_id": corpus_id, "corpus_revision": revision}
    sample = await rt.db.source_chunks.find_one(scope)
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": rt.s.vector_index_name,
                    "path": "embedding",
                    "queryVector": sample["embedding"],
                    "filter": scope,
                    "limit": expected,
                    "numCandidates": min(10000, max(100, expected * 2)),
                }
            },
            {"$count": "n"},
        ]
        rows = await (await rt.db.source_chunks.aggregate(pipeline)).to_list()
        vector_ready = bool(rows and rows[0]["n"] == expected)
        lexical_ready = True
        if rt.s.retrieval_mode != "vector":
            rows = await (
                await rt.db.source_chunks.aggregate(
                    [
                        {
                            "$searchMeta": {
                                "index": rt.s.search_index_name,
                                "compound": {
                                    "filter": [{"equals": {"path": k, "value": v}} for k, v in scope.items()]
                                },
                                "count": {"type": "total"},
                            }
                        }
                    ]
                )
            ).to_list()
            lexical_ready = bool(rows and rows[0]["count"]["total"] == expected)
        if vector_ready and lexical_ready:
            return
        await asyncio.sleep(2)
    raise TimeoutError(
        "New corpus is not completely searchable; revision was not published. Rerun ingestion."
    )


async def ingest(rt, chunks, corpus_id):
    if not chunks or len(chunks) > 5000:
        raise ValueError("MVP ingestion supports 1..5000 chunks")
    revision = digest(
        {
            "chunks": [c.model_dump() for c in chunks],
            "embedding_model": rt.s.voyage_model,
            "dimensions": rt.s.embedding_dimensions,
        }
    )
    costs = []
    # Immutable revision IDs let current readers finish while a new revision is indexed.
    for offset in range(0, len(chunks), 64):
        batch = chunks[offset : offset + 64]
        ids = [digest([corpus_id, revision, c.id]) for c in batch]
        existing = {
            r["_id"] for r in await rt.db.source_chunks.find({"_id": {"$in": ids}}, {"_id": 1}).to_list()
        }
        pending = [(c, key) for c, key in zip(batch, ids) if key not in existing]
        if not pending:
            continue
        vectors, u = await rt.voyage.embed([c.text for c, _ in pending], "document")
        costs.append(u.model_dump())
        operations = []
        for (chunk, key), embedding in zip(pending, vectors):
            doc = chunk.model_dump(exclude={"id"})
            doc.update(
                {
                    "_id": key,
                    "original_id": chunk.id,
                    "corpus_id": corpus_id,
                    "corpus_revision": revision,
                    "embedding": embedding,
                }
            )
            operations.append(UpdateOne({"_id": key}, {"$setOnInsert": doc}, upsert=True))
        await rt.db.source_chunks.bulk_write(operations, ordered=False)
    await setup(rt.db, rt.s)
    await wait_searchable(rt, corpus_id, revision, len(chunks))
    await rt.db.corpora.replace_one(
        {"_id": corpus_id},
        {
            "_id": corpus_id,
            "revision": revision,
            "status": "ready",
            "num_chunks": len(chunks),
            "embedding_model": rt.s.voyage_model,
            "embedding_dimensions": rt.s.embedding_dimensions,
            "updated_at": datetime.now(timezone.utc),
        },
        upsert=True,
    )
    return {"corpus_id": corpus_id, "revision": revision, "num_chunks": len(chunks), "ingestion_usage": costs}


async def main():
    parser = argparse.ArgumentParser(description="Ingest the authoritative local PDF into Atlas")
    parser.add_argument("pdf", nargs="?")
    parser.add_argument("--corpus-id", default="hackathon_pdf")
    args = parser.parse_args()
    chunks = parse_pdf(args.pdf or find_pdf())
    s = Settings()
    missing = [k for k in s.missing() if k != "OPENROUTER_API_KEY"]
    if missing:
        raise SystemExit("Missing " + ", ".join(missing) + f"; parsed {len(chunks)} PDF chunks successfully")
    async with runtime(s) as rt:
        print(json.dumps(await ingest(rt, chunks, args.corpus_id), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
