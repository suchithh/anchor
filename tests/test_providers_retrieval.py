import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from src.models import Judgment
from src.providers import Voyage
from src.retrieval.atlas import AtlasRetriever
from src.retrieval.fusion import reciprocal_rank_fusion
from src.verification.jev import JevVerifier
from src.verification.llm import ContextBudgetExceeded, LLMVerifier
from tests.conftest import AsyncCursor


async def test_jev_documented_wire_contract(settings, request_model, chunk):
    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/alpha/decisions"
        body = json.loads(request.content)
        question = body["questions"]["grounding"]
        assert question["type"] == "choice"
        assert set(question["criteria"]) == {"SUPPORTED", "CONTRADICTED", "INSUFFICIENT"}
        assert body["state"]["evidence"][0]["page"] == 1
        assert body["state"]["claim"] == request_model.claim
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
                "usage": {"input_tokens": 100, "output_tokens": 5, "cost": 0.0001},
                "model": "jev-snapshot",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result, usage = await JevVerifier(client, settings).judge(request_model, [chunk])
        assert result.p_supported == 0.8
        assert usage.cost == 0.0001 and usage.model == "jev-snapshot"
        assert client.grounding_calls[0]["input_tokens"] == 100


@pytest.mark.parametrize(
    "probabilities",
    [
        {"p_supported": 2, "p_contradicted": 0, "p_insufficient": 0},
        {"p_supported": float("nan"), "p_contradicted": 0, "p_insufficient": 0},
        {"p_supported": 0.6, "p_contradicted": 0.6, "p_insufficient": 0.6},
        {"p_supported": 0.1, "p_contradicted": 0.8, "p_insufficient": 0.1},
    ],
)
def test_invalid_probabilities_rejected(probabilities):
    with pytest.raises(ValueError):
        Judgment(verdict="SUPPORTED", **probabilities)


async def test_provider_error_counted_never_a_verdict(settings, request_model):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429))) as client:
        with pytest.raises(RuntimeError, match="429"):
            await JevVerifier(client, settings).judge(request_model, [])
        assert len(client.grounding_calls) == 1
        assert client.grounding_calls[0]["cost"] is None


async def test_provider_overall_deadline_cancels_stalled_response(settings, request_model):
    cancelled = asyncio.Event()

    async def handler(request):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=0.01) as client:
        with pytest.raises(asyncio.TimeoutError):
            await JevVerifier(client, settings).judge(request_model, [])
        assert cancelled.is_set()
        assert len(client.grounding_calls) == 1
        assert client.grounding_calls[0]["status"] == "failed"
        assert client.grounding_calls[0]["cost"] is None


async def test_llm_structured_response_and_missing_ids(settings, request_model, chunk):
    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"]["json_schema"]["strict"]
        assert body["provider"]["require_parameters"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"judgments": [{"claim_id": "wrong", "verdict": "SUPPORTED"}]}
                            )
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="claim_id"):
            await LLMVerifier(client, settings).judge(request_model, [chunk])


async def test_posthoc_one_call_and_shared_context(settings, request_model, chunk):
    def handler(request):
        states = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert len(states) == 2
        assert "shared_evidence_for_all_claims" in states[0]
        assert "shared_evidence_for_all_claims" not in states[1]
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
                                        {"claim_id": s["claim_id"], "verdict": "INSUFFICIENT"} for s in states
                                    ]
                                }
                            )
                        },
                    }
                ],
                "usage": {"cost": 0.02, "prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verifier = LLMVerifier(client, settings)
        requests = [request_model, request_model.model_copy(update={"claim_id": "c2"})]
        judgments, usage = await verifier.posthoc(requests, [chunk])
        assert len(client.grounding_calls) == 1 and usage.cost == 0.02
        assert judgments["c1"].probability_kind == "one_hot_label"
        verifier.s = settings.model_copy(update={"posthoc_max_input_bytes": 1})
        with pytest.raises(ContextBudgetExceeded):
            await verifier.posthoc(requests, [chunk])
        assert len(client.grounding_calls) == 1


async def test_voyage_embedding_order_and_unknown_cost(settings):
    settings = settings.model_copy(update={"embedding_dimensions": 2})

    def handler(request):
        body = json.loads(request.content)
        assert body["input_type"] == "query" and body["truncation"] is False
        return httpx.Response(
            200,
            json={
                "data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}],
                "usage": {"total_tokens": 5},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vectors, usage = await Voyage(client, settings).embed(["a", "b"], "query")
        assert vectors == [[1, 0], [0, 1]]
        assert usage.input_tokens == 5 and usage.cost is None


def test_rrf_deduplicates_and_is_deterministic():
    a, b, c = [{"_id": k} for k in "abc"]
    assert reciprocal_rank_fusion([[a, b, a], [b, c]], 3) == [b, a, c]


async def test_atlas_scope_before_search_and_reranker_off(settings, chunk):
    pipelines = []

    async def aggregate(pipeline):
        pipelines.append(pipeline)
        return AsyncCursor(iter([{"_id": chunk.id, **chunk.model_dump(exclude={"id"})}]))

    async def embed(texts, input_type):
        from src.models import Usage

        return [[1, 0]], Usage(provider="test", operation="embedding")

    rt = AtlasRetriever(
        SimpleNamespace(source_chunks=SimpleNamespace(aggregate=aggregate)),
        SimpleNamespace(embed=embed),
        settings,
    )
    bundle = await rt.retrieve_evidence("claim", {"corpus_id": "tenant", "version": "v2"}, "revision")
    spec = pipelines[0][0]["$vectorSearch"]
    assert spec["filter"] == {"corpus_id": "tenant", "version": "v2", "corpus_revision": "revision"}
    assert spec["limit"] == 3
    assert bundle.chunks[0].id == chunk.id and bundle.reranker_latency_ms == 0
