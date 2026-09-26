import argparse
import asyncio
from time import monotonic

from pymongo.operations import SearchIndexModel

from src.config import Settings
from src.runtime import runtime


async def setup(db, s, wait_seconds=180):
    await db.source_chunks.create_index([("corpus_id", 1), ("corpus_revision", 1)])
    await db.verified_claims.create_index("claim_hash")
    await db.grounding_runs.create_index("run_id", unique=True)
    fields = ["corpus_id", "corpus_revision", "source_id", "version"]
    models = [
        SearchIndexModel(
            name=s.vector_index_name,
            type="vectorSearch",
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": s.embedding_dimensions,
                        "similarity": "cosine",
                    },
                    *[{"type": "filter", "path": f} for f in fields],
                ]
            },
        )
    ]
    if s.retrieval_mode != "vector":
        models.append(
            SearchIndexModel(
                name=s.search_index_name,
                definition={
                    "mappings": {
                        "dynamic": False,
                        "fields": {"text": {"type": "string"}, **{f: {"type": "token"} for f in fields}},
                    }
                },
            )
        )
    existing = {i["name"]: i for i in await (await db.source_chunks.list_search_indexes()).to_list()}
    for model in models:
        spec = model.document
        if spec["name"] not in existing:
            await db.source_chunks.create_search_index(model=model)
        elif existing[spec["name"]].get("latestDefinition") != spec["definition"]:
            raise ValueError(f"Index {spec['name']} has a different definition; use a new index name")
    deadline = monotonic() + wait_seconds
    while monotonic() < deadline:
        rows = await (await db.source_chunks.list_search_indexes()).to_list()
        states = {r["name"]: r for r in rows}
        if all(states.get(m.document["name"], {}).get("queryable") for m in models):
            return {
                name: {"status": value.get("status"), "queryable": value.get("queryable")}
                for name, value in states.items()
            }
        if any(r.get("status") == "FAILED" for r in rows):
            raise RuntimeError("Atlas search index build failed; inspect Atlas index status")
        await asyncio.sleep(2)
    raise TimeoutError("Atlas indexes are not queryable yet; rerun setup after checking Atlas")


async def main():
    argparse.ArgumentParser(description="Create and wait for Atlas indexes (no data deletion)").parse_args()
    s = Settings()
    if not s.mongodb_uri.get_secret_value():
        raise SystemExit("Missing MONGODB_URI (use the emailed Atlas Hackathon Sandbox)")
    async with runtime(s) as rt:
        print(await setup(rt.db, s))


if __name__ == "__main__":
    asyncio.run(main())
