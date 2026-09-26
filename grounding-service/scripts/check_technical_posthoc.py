"""Full-context reference check while ingestion is unavailable; not an Atlas pipeline benchmark."""

import asyncio
import json
from pathlib import Path
from time import perf_counter

import httpx

from benchmarks.generate_technical_dataset import generate
from src.config import Settings
from src.models import VerificationRequest
from src.technical_corpus import load_corpus
from src.util import elapsed
from src.verification.llm import LLMVerifier


async def main():
    s = Settings()
    chunks, _ = load_corpus()
    fixtures = generate()["claims"]
    requests = [
        VerificationRequest(
            run_id="full-context-reference", claim_id=r["claim_id"], claim=r["claim"], scope=r["scope"]
        )
        for r in fixtures
    ]
    report = {
        "type": "standalone_full_context_reference",
        "model": s.baseline_model,
        "num_chunks": len(chunks),
        "num_claims": len(requests),
        "limitations": "No Atlas ingestion/retrieval/persistence; not comparable to end-to-end benchmark latency",
    }
    async with httpx.AsyncClient(timeout=180) as client:
        tick = perf_counter()
        try:
            results, usage = await LLMVerifier(client, s).posthoc(requests, chunks)
            report.update(
                {
                    "status": "completed",
                    "verifier_wall_ms": elapsed(tick),
                    "usage": usage.model_dump(),
                    "accuracy": sum(results[r["claim_id"]].verdict.value == r["gold_label"] for r in fixtures)
                    / len(fixtures),
                    "records": [
                        {
                            "claim_id": r["claim_id"],
                            "claim": r["claim"],
                            "gold_label": r["gold_label"],
                            "verdict": results[r["claim_id"]].verdict.value,
                        }
                        for r in fixtures
                    ],
                }
            )
        except Exception as exc:  # noqa: BLE001 - preserve failed reference calls and costs
            report.update(
                {"status": "failed", "error": type(exc).__name__, "verifier_wall_ms": elapsed(tick)}
            )
        report["calls"] = getattr(client, "grounding_calls", [])
    Path("benchmarks/results/technical_posthoc_reference.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k not in {"records", "calls"}}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
