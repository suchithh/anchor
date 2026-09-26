from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.config import Settings
from src.grounding.store import RunConflict
from src.models import Chunk, VerificationRequest, VerificationResult
from src.retrieval.atlas import chunk_from_document
from src.runtime import runtime
from src.util import digest


@asynccontextmanager
async def lifespan(app):
    settings = Settings()
    missing = settings.missing(baseline=settings.verifier == "llm")
    if missing:
        raise RuntimeError("Missing configuration: " + ", ".join(missing))
    async with runtime(settings) as rt:
        app.state.runtime = rt
        app.state.service = rt.service(settings.verifier)
        yield


app = FastAPI(title="Running grounding verifier", lifespan=lifespan)


class Batch(BaseModel):
    requests: list[VerificationRequest] = Field(min_length=1, max_length=200)
    max_concurrency: int = Field(8, ge=1, le=128)


@app.post("/verify", response_model=VerificationResult)
async def verify(request: VerificationRequest):
    try:
        return await app.state.service.verify(request)
    except RunConflict as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(502, "Verification failed; no judgment substituted") from e


@app.post("/verify/batch")
async def batch(request: Batch):
    results = await app.state.service.verify_batch(
        request.requests,
        min(request.max_concurrency, app.state.runtime.s.max_concurrency),
        return_exceptions=True,
    )
    return {
        "results": [
            {"claim_id": r.claim_id, "result": item.model_dump(mode="json")}
            if isinstance(item, VerificationResult)
            else {"claim_id": r.claim_id, "error": type(item).__name__}
            for r, item in zip(request.requests, results)
        ]
    }


@app.get("/runs/{run_id}")
async def run(run_id: str, include_events: bool = False):
    result = await app.state.runtime.runs.get(run_id, include_events=include_events)
    if result is None:
        raise HTTPException(404, "Unknown run")
    return result


@app.get("/runs/{run_id}/claims/{claim_id}/evidence", response_model=list[Chunk])
async def evidence(run_id: str, claim_id: str):
    """Expose the persisted judgment's actual source chunks for harness correction."""
    run = await app.state.runtime.runs.get(run_id, include_events=True)
    event = run.get("events", {}).get(digest(claim_id)) if run else None
    if not event:
        raise HTTPException(404, "Unknown verified claim")
    result = event["result"]
    docs = await app.state.runtime.db.source_chunks.find(
        {"_id": {"$in": result["evidence_ids"]},
         "corpus_id": run["provenance"]["corpus_id"],
         "corpus_revision": result["corpus_revision"]},
        {"embedding": 0},
    ).to_list(length=None)
    return [chunk_from_document(doc) for doc in docs]
