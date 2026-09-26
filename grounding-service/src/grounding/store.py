from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from src.grounding.cache import request_fingerprint
from src.util import digest


class RunConflict(ValueError):
    pass


class MongoRuns:
    """Atomic update pipeline: score and deduplication commit together.

    Bounded to 2,000 claims/run for the MVP; events belong in a transactional
    collection before expanding to truly long-running production sessions.
    """

    def __init__(self, db, alpha):
        self.collection, self.alpha = db.grounding_runs, alpha

    async def get(self, run_id, include_events=False):
        projection = {"_id": 0} if include_events else {"_id": 0, "events": 0}
        return await self.collection.find_one({"_id": run_id}, projection)

    async def previous(self, request, provenance):
        key = digest(request.claim_id)
        run = await self.collection.find_one({"_id": request.run_id}, {"provenance": 1, f"events.{key}": 1})
        if not run:
            return None
        if run["provenance"] != provenance:
            raise RunConflict(
                "A run cannot mix corpus revisions or verifier/scoring policies; use a new run_id"
            )
        event = run.get("events", {}).get(key)
        if event and event["fingerprint"] != request_fingerprint(request):
            raise RunConflict("claim_id already used for a different request in this run")
        return event["result"] if event else None

    async def record(self, request, result, provenance):
        initial = {
            "run_id": request.run_id,
            "revision": 0,
            "num_claims": 0,
            "num_cache_hits": 0,
            "events": {},
            "provenance": provenance,
        }
        try:
            await self.collection.update_one({"_id": request.run_id}, {"$setOnInsert": initial}, upsert=True)
        except DuplicateKeyError:
            pass
        key = digest(request.claim_id)
        scores = {}
        for field, value in zip(
            ("grounding_score", "contradiction_score", "insufficient_score"), result.probabilities()
        ):
            scores[field] = {
                "$cond": [
                    {"$eq": ["$num_claims", 0]},
                    value,
                    {"$add": [{"$multiply": [self.alpha, "$" + field]}, (1 - self.alpha) * value]},
                ]
            }
        # MongoDB re-evaluates the predicate against the current document and
        # computes the EWMA on the server, avoiding competing read/CAS retries.
        outcome = await self.collection.update_one(
            {
                "_id": request.run_id,
                "provenance": provenance,
                "num_claims": {"$lt": 2000},
                f"events.{key}": {"$exists": False},
            },
            [
                {
                    "$set": {
                        **scores,
                        "revision": {"$add": ["$revision", 1]},
                        "num_claims": {"$add": ["$num_claims", 1]},
                        "num_cache_hits": {"$add": ["$num_cache_hits", int(result.cache_hit)]},
                        "updated_at": datetime.now(timezone.utc),
                        f"events.{key}": {
                            "claim_id": {"$literal": request.claim_id},
                            "fingerprint": {"$literal": request_fingerprint(request)},
                            "result": {"$literal": result.model_dump(mode="json")},
                            "commit_sequence": {"$add": ["$num_claims", 1]},
                            "score_after": scores,
                            "committed_at": datetime.now(timezone.utc),
                        },
                    }
                }
            ],
        )
        if outcome.modified_count:
            return True
        if await self.previous(request, provenance) is not None:
            return False
        raise RunConflict("MVP limit: 2000 distinct claims/run; create a new run")
