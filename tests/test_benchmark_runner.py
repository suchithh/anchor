import json

import httpx

from benchmarks.runners import run_dataset
from src.runtime import Runtime
from tests.conftest import FakeRetriever


async def test_full_benchmark_orchestration_with_mock_providers(db, settings, chunk):
    """Exercise all approaches and warm reuse without producing fictional benchmark artifacts."""
    s = settings.model_copy(update={"baseline_model": "test/model"})
    await db.corpora.insert_one(
        {
            "_id": "test",
            "revision": "rev1",
            "status": "ready",
            "embedding_model": s.voyage_model,
            "embedding_dimensions": s.embedding_dimensions,
        }
    )
    await db.source_chunks.insert_one(
        {"_id": chunk.id, **chunk.model_dump(exclude={"id"}), "corpus_id": "test", "corpus_revision": "rev1"}
    )

    def handler(request):
        body = json.loads(request.content)
        if request.url.path.endswith("decisions"):
            return httpx.Response(
                200,
                json={
                    "answers": {
                        "grounding": {
                            "type": "choice",
                            "choice": "SUPPORTED",
                            "probabilities": {"SUPPORTED": 0.8, "CONTRADICTED": 0.1, "INSUFFICIENT": 0.1},
                        }
                    },
                    "usage": {"cost": 0.001, "input_tokens": 20, "output_tokens": 1},
                },
            )
        states = json.loads(body["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "judgments": [
                                        {"claim_id": st["claim_id"], "verdict": "SUPPORTED"} for st in states
                                    ]
                                }
                            )
                        },
                    }
                ],
                "usage": {"cost": 0.01, "prompt_tokens": 100, "completion_tokens": 10},
            },
        )

    fixtures = [
        {
            "claim_id": f"c{i}",
            "claim": f"Fact {i}",
            "scope": {"corpus_id": "test"},
            "gold_label": "SUPPORTED",
            "gold_pages": [1],
            "gold_quote": "A fact.",
        }
        for i in range(3)
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rt = Runtime(db, client, s)
        rt.retriever = FakeRetriever(chunk)
        rows = await run_dataset(
            rt,
            fixtures,
            {"corpus_id": "test", "revision": "rev1", "num_chunks": 1},
            repetitions=1,
            seed=42,
            benchmark_id="mock_only",
        )
    assert len(rows) == 6 and all(r["status"] == "completed" for r in rows)
    warm = next(r for r in rows if r["phase"] == "warm")
    assert warm["metrics"]["cache_hit_rate"] == 1
    assert warm["metrics"]["cost"]["api_calls"] == 0
    posthoc = next(r for r in rows if r["approach"] == "llm_posthoc")
    assert posthoc["metrics"]["cost"]["api_calls"] == 1
    assert posthoc["metrics"]["cost"]["total_cost"] == 0.01
    assert posthoc["metrics"]["async_overlap_ratio"] is None
    for row in rows:
        if row["phase"] == "cold" and row["approach"] != "llm_posthoc":
            assert row["metrics"]["cost"]["api_calls"] == 3
            assert row["evidence"]["judged_evidence_hit_rate"] == 1
