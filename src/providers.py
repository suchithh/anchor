import asyncio
from typing import Protocol

import httpx

from src.models import Usage


class Embeddings(Protocol):
    async def embed(self, texts: list[str], input_type: str) -> tuple[list[list[float]], Usage]: ...


async def post(client, url, key, payload):
    # No invisible retry: failures remain visible in benchmark coverage/call accounting.
    if not hasattr(client, "grounding_calls"):
        client.grounding_calls = []
    entry = {
        "provider": "voyage" if "voyageai.com" in url else "openrouter",
        "operation": url.rsplit("/", 1)[-1],
        "model": payload.get("model"),
        "calls": 1,
        "input_tokens": None,
        "output_tokens": None,
        "cost": None,
        "cost_kind": "unavailable",
        "status": "failed",
    }
    client.grounding_calls.append(entry)
    # httpx's read timeout resets whenever bytes arrive. Provider keep-alives must
    # not extend a verification indefinitely; also bound the complete request.
    response = await asyncio.wait_for(
        client.post(url, headers={"Authorization": f"Bearer {key}"}, json=payload),
        timeout=client.timeout.read,
    )
    entry["http_status"] = response.status_code
    entry["rate_limit_headers"] = {
        k: v for k, v in response.headers.items() if "ratelimit" in k.lower() or k.lower() == "retry-after"
    }
    if response.is_error:
        # Provider error bodies can echo inputs or credentials; do not print them.
        raise RuntimeError(f"{httpx.URL(url).host} returned HTTP {response.status_code}")
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"{httpx.URL(url).host} returned an API error")
    entry.update(usage(data, entry["provider"], entry["operation"], payload.get("model")).model_dump())
    entry["status"] = "http_success"
    return data


def usage(data, provider, operation, model, rate=None):
    u = data.get("usage") or {}
    tokens = u.get("input_tokens", u.get("prompt_tokens", u.get("total_tokens")))
    cost = u.get("cost")
    kind = "actual" if cost is not None else "unavailable"
    if cost is None and rate is not None and tokens is not None:
        cost, kind = tokens * rate / 1_000_000, "ESTIMATED"
    return Usage(
        provider=provider,
        operation=operation,
        input_tokens=tokens,
        output_tokens=u.get("output_tokens", u.get("completion_tokens")),
        cost=cost,
        cost_kind=kind,
        model=data.get("model", model),
    )


class Voyage:
    def __init__(self, client, settings):
        self.client, self.s = client, settings

    async def embed(self, texts, input_type):
        data = await post(
            self.client,
            "https://api.voyageai.com/v1/embeddings",
            self.s.voyage_api_key.get_secret_value(),
            {
                "model": self.s.voyage_model,
                "input": texts,
                "input_type": input_type,
                "output_dimension": self.s.embedding_dimensions,
                "truncation": False,
            },
        )
        rows = sorted(data["data"], key=lambda r: r["index"])
        if [r["index"] for r in rows] != list(range(len(texts))):
            raise ValueError("Incomplete embedding response")
        vectors = [r["embedding"] for r in rows]
        if any(len(v) != self.s.embedding_dimensions for v in vectors):
            raise ValueError("Embedding dimension mismatch")
        return vectors, usage(
            data, "voyage", "embedding", self.s.voyage_model, self.s.voyage_usd_per_million_tokens
        )

    async def rerank(self, claim, chunks, top_k):
        data = await post(
            self.client,
            "https://api.voyageai.com/v1/rerank",
            self.s.voyage_api_key.get_secret_value(),
            {
                "model": self.s.voyage_rerank_model,
                "query": claim,
                "documents": [c.text for c in chunks],
                "top_k": top_k,
                "truncation": False,
            },
        )
        indices = [r["index"] for r in data["data"]]
        if len(set(indices)) != len(indices) or any(i < 0 or i >= len(chunks) for i in indices):
            raise ValueError("Invalid reranking indices")
        return [chunks[i] for i in indices], usage(
            data, "voyage", "rerank", self.s.voyage_rerank_model, self.s.voyage_rerank_usd_per_million_tokens
        )
