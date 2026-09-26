import asyncio

import pytest

from src.grounding.cache import VerifiedCache, cache_key
from src.grounding.score import ewma
from src.grounding.service import GroundingService
from src.grounding.store import MongoRuns, RunConflict
from src.models import Judgment, VerificationResult
from tests.conftest import FakeRetriever, FakeVerifier


def test_ewma():
    assert ewma(None, [0.8, 0.1, 0.1]) == [0.8, 0.1, 0.1]
    assert ewma([1, 0, 0], [0, 1, 0]) == pytest.approx([0.8, 0.2, 0])
    assert sum(ewma([0.8, 0.1, 0.1], [0.1, 0.2, 0.7])) == pytest.approx(1)
    with pytest.raises(ValueError):
        ewma(None, [1, 0, 0], 1)


def test_cache_key_boundaries(request_model):
    key = cache_key(request_model, "rev1", "jev")
    for change in [
        {"context": "different meaning"},
        {"scope": {"corpus_id": "other"}},
        {"claim": "a fact."},
        {"claim": "A fact?"},
    ]:
        assert cache_key(request_model.model_copy(update=change), "rev1", "jev") != key
    assert cache_key(request_model, "rev2", "jev") != key
    assert cache_key(request_model, "rev1", "llm") != key
    assert cache_key(request_model.model_copy(update={"claim": " A  fact. "}), "rev1", "jev") == key


async def make_service(db, settings, chunk):
    await db.corpora.insert_one(
        {
            "_id": "test",
            "revision": "rev1",
            "status": "ready",
            "embedding_model": settings.voyage_model,
            "embedding_dimensions": settings.embedding_dimensions,
        }
    )
    await db.source_chunks.insert_one(
        {"_id": chunk.id, **chunk.model_dump(exclude={"id"}), "corpus_id": "test", "corpus_revision": "rev1"}
    )
    return GroundingService(
        db, FakeRetriever(chunk), FakeVerifier(), VerifiedCache(db), MongoRuns(db, 0.8), settings
    )


async def test_cache_warm_and_changed_evidence(db, settings, chunk, request_model):
    service = await make_service(db, settings, chunk)
    cold = await service.verify(request_model)
    warm = await service.verify(request_model.model_copy(update={"run_id": "second"}))
    assert not cold.cache_hit and warm.cache_hit
    assert warm.verifier_cost == 0 and warm.usage == []
    assert service.verifier.calls == 1
    await db.source_chunks.update_one({"_id": chunk.id}, {"$set": {"content_hash": "changed"}})
    third = await service.verify(request_model.model_copy(update={"run_id": "third"}))
    assert not third.cache_hit


async def test_deleted_evidence_invalidates(db, settings, chunk, request_model):
    service = await make_service(db, settings, chunk)
    await service.verify(request_model)
    key = cache_key(request_model, "rev1", service.policy)
    await db.source_chunks.delete_one({"_id": chunk.id})
    assert await service.cache.get(key, request_model.scope, "rev1") is None


async def test_new_corpus_revision_invalidates_even_without_changed_evidence(
    db, settings, chunk, request_model
):
    service = await make_service(db, settings, chunk)
    await service.verify(request_model)
    await db.corpora.update_one({"_id": "test"}, {"$set": {"revision": "rev2"}})
    with pytest.raises(RunConflict):
        await service.verify(request_model)
    result = await service.verify(request_model.model_copy(update={"run_id": "new_revision"}))
    assert not result.cache_hit


async def test_idempotency_and_conflicting_ids(db, settings, chunk, request_model):
    service = await make_service(db, settings, chunk)
    results = await asyncio.gather(*(service.verify(request_model) for _ in range(8)))
    run = await service.runs.get("test")
    assert run["num_claims"] == 1
    assert sum(not r.deduplicated for r in results) == 1
    replay = await service.verify(request_model)
    assert replay.deduplicated and not replay.usage
    with pytest.raises(RunConflict):
        await service.verify(request_model.model_copy(update={"claim": "Different fact"}))


async def test_concurrency_and_no_lost_score_updates(db, settings, chunk, request_model):
    service = await make_service(db, settings, chunk)
    service.cache_enabled = False
    requests = [request_model.model_copy(update={"claim_id": f"c{i}"}) for i in range(24)]
    results = await service.verify_batch(requests, max_concurrency=4)
    assert len(results) == 24
    assert 1 < service.verifier.peak <= 4
    run = await service.runs.get("test")
    assert run["num_claims"] == run["revision"] == 24
    assert run["grounding_score"] == pytest.approx(0.8)


async def test_failure_does_not_score_or_cache(db, settings, chunk, request_model):
    service = await make_service(db, settings, chunk)

    async def fail(*args):
        raise RuntimeError("provider down")

    service.verifier.judge = fail
    with pytest.raises(RuntimeError):
        await service.verify(request_model)
    assert await service.runs.get("test") is None
    assert await db.verified_claims.count_documents({}) == 0


async def test_zero_concurrency_rejected(db, settings, chunk, request_model):
    service = await make_service(db, settings, chunk)
    with pytest.raises(ValueError, match="positive"):
        await service.verify_batch([request_model], max_concurrency=0)


async def test_atomic_score_pipeline_matches_ordered_ewma_and_literal_ids(db, request_model):
    runs = MongoRuns(db, 0.8)
    expected = None
    for i, label in enumerate(["SUPPORTED", "CONTRADICTED", "INSUFFICIENT"]):
        request = request_model.model_copy(update={"claim_id": f"$literal-{i}"})
        judgment = Judgment.hard(label)
        result = VerificationResult(
            **judgment.model_dump(),
            run_id=request.run_id,
            claim_id=request.claim_id,
            corpus_revision="test",
            verifier="test",
            evidence_ids=[],
        )
        assert await runs.record(request, result, {"policy": "test"})
        assert not await runs.record(request, result, {"policy": "test"})
        expected = ewma(expected, judgment.probabilities(), 0.8)
    stored = await runs.get(request.run_id, include_events=True)
    assert stored["num_claims"] == 3
    assert [
        stored[k] for k in ["grounding_score", "contradiction_score", "insufficient_score"]
    ] == pytest.approx(expected)
    assert {e["claim_id"] for e in stored["events"].values()} == {"$literal-0", "$literal-1", "$literal-2"}
