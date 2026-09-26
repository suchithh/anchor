from src.util import digest, normalize


def cache_key(request, revision, policy):
    return digest(
        {
            "claim": normalize(request.claim),
            "context": request.context,
            "scope": request.scope,
            "revision": revision,
            "policy": policy,
        }
    )


def request_fingerprint(request):
    return digest(request.model_dump(exclude={"run_id", "claim_id"}))


class VerifiedCache:
    def __init__(self, db):
        self.db = db

    async def get(self, key, scope, revision):
        doc = await self.db.verified_claims.find_one({"_id": key})
        if not doc:
            return None
        expected = dict(zip(doc["evidence_ids"], doc["source_hashes"]))
        rows = await self.db.source_chunks.find(
            {"_id": {"$in": list(expected)}, **scope, "corpus_revision": revision}, {"content_hash": 1}
        ).to_list(length=None)
        actual = {r["_id"]: r["content_hash"] for r in rows}
        return doc if actual == expected else None

    async def put(self, key, document):
        await self.db.verified_claims.replace_one({"_id": key}, {"_id": key, **document}, upsert=True)
