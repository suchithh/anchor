"""Small live contract check. Never print credentials or arbitrary provider error bodies."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from src.config import Settings
from src.models import Chunk, VerificationRequest
from src.providers import Voyage
from src.util import digest
from src.verification.jev import JevVerifier
from src.verification.llm import LLMVerifier


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model")
    p.add_argument("--catalog-only", action="store_true")
    p.add_argument("--voyage-diagnostics", action="store_true")
    p.add_argument("--voyage-batch-diagnostics", action="store_true")
    a = p.parse_args()
    s = Settings(**({"baseline_model": a.model} if a.model else {}))
    async with httpx.AsyncClient(timeout=90) as client:
        if a.voyage_diagnostics or a.voyage_batch_diagnostics:
            texts = ["rate limit connectivity check"]
            if a.voyage_batch_diagnostics:
                from src.technical_corpus import load_corpus

                chunks, _ = load_corpus()
                texts = [c.text for c in chunks[:64]]
            response = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": "Bearer " + s.voyage_api_key.get_secret_value()},
                json={"model": s.voyage_model, "input": texts, "input_type": "document"},
            )
            print("Voyage HTTP status:", response.status_code)
            if response.is_error:
                safe = response.text.replace(s.voyage_api_key.get_secret_value(), "[REDACTED]")
                print(safe[:1500])
            else:
                print("Single-query embedding succeeded")
            return
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        models = [
            m
            for m in response.json()["data"]
            if m["id"].startswith("deepseek/") or m["id"] in {s.jev_model, "google/gemini-2.5-flash-lite"}
        ]
        catalog = [
            {
                "id": m["id"],
                "context_length": m.get("context_length"),
                "pricing": m.get("pricing"),
                "supported_parameters": m.get("supported_parameters"),
            }
            for m in models
        ]
        auth = {"Authorization": "Bearer " + s.openrouter_api_key.get_secret_value()}
        balance = await client.get("https://openrouter.ai/api/v1/credits", headers=auth)
        balances = balance.json().get("data", {}) if balance.is_success else {"status": balance.status_code}
        print(
            json.dumps(
                {
                    "catalog": [
                        {
                            "id": m["id"],
                            "context_length": m["context_length"],
                            "input_per_million": float(m["pricing"]["prompt"]) * 1e6,
                            "output_per_million": float(m["pricing"]["completion"]) * 1e6,
                            "structured_outputs": "structured_outputs" in (m["supported_parameters"] or []),
                        }
                        for m in catalog
                    ],
                    "credits": balances,
                },
                indent=2,
            ),
            flush=True,
        )
        if a.catalog_only:
            return
        sample = Chunk(
            id="smoke",
            text="The service timeout for Package-A v2 is 20 seconds.",
            source_id="smoke",
            source_type="synthetic",
            source_uri="smoke://sample",
            version="v2",
            content_hash=digest("smoke"),
        )
        request = VerificationRequest(
            run_id="live-contract",
            claim_id="smoke",
            claim="Package-A v2 has a timeout of 20 seconds.",
            scope={"corpus_id": "smoke"},
        )
        results = {}
        for name, call in [
            ("voyage", lambda: Voyage(client, s).embed([sample.text], "document")),
            ("jev", lambda: JevVerifier(client, s).judge(request, [sample])),
            ("llm", lambda: LLMVerifier(client, s).judge(request, [sample])),
        ]:
            try:
                value, u = await call()
                results[name] = {
                    "status": "ok",
                    "usage": u.model_dump(),
                    "verdict": value.verdict.value if name != "voyage" else None,
                    "dimensions": len(value[0]) if name == "voyage" else None,
                }
            except Exception as exc:  # noqa: BLE001 - report each independent smoke test
                results[name] = {
                    "status": "failed",
                    "error": type(exc).__name__,
                    "detail": str(exc) if type(exc) in {RuntimeError, KeyError} else None,
                }
            print(json.dumps({name: results[name]}), flush=True)
        target = Path("benchmarks/results/live_preflight.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "catalog": catalog,
                    "credits_before": balances,
                    "checks": results,
                    "calls": getattr(client, "grounding_calls", []),
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    asyncio.run(main())
