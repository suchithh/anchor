from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.main import app, evidence
from src.grounding.store import MongoRuns
from src.util import digest


async def test_pi_evidence_uses_persisted_ids_and_revision(db, chunk, monkeypatch):
    await db.source_chunks.insert_one({
        **chunk.model_dump(exclude={"id"}), "_id": chunk.id,
        "corpus_id": "test", "corpus_revision": "v1", "embedding": [0.1],
    })
    await db.grounding_runs.insert_one({
        "_id": "run", "provenance": {"corpus_id": "test"},
        "events": {digest("claim"): {"result": {
            "evidence_ids": [chunk.id], "corpus_revision": "v1",
        }}},
    })
    monkeypatch.setattr(app.state, "runtime", SimpleNamespace(db=db, runs=MongoRuns(db, 0.8)), raising=False)
    assert await evidence("run", "claim") == [chunk]
    with pytest.raises(HTTPException) as error:
        await evidence("run", "missing")
    assert error.value.status_code == 404
    await db.source_chunks.update_one({"_id": chunk.id}, {"$set": {"corpus_revision": "v2"}})
    assert await evidence("run", "claim") == []
