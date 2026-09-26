from contextlib import asynccontextmanager

import httpx
from pymongo import AsyncMongoClient

from src.grounding.cache import VerifiedCache
from src.grounding.service import GroundingService
from src.grounding.store import MongoRuns
from src.providers import Voyage
from src.retrieval.atlas import AtlasRetriever
from src.verification.jev import JevVerifier
from src.verification.llm import LLMVerifier


@asynccontextmanager
async def runtime(settings):
    mongo = AsyncMongoClient(
        settings.mongodb_uri.get_secret_value(),
        serverSelectionTimeoutMS=15000,  # Bound discovery of this remote Atlas replica set.
        # Observed queries/writes take well below a second; 30s permits network
        # variation and ingestion while bounding the entire DB operation.
        timeoutMS=settings.mongodb_timeout_ms,
    )
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        limits=httpx.Limits(max_connections=settings.max_concurrency * 3),
    ) as http:
        try:
            db = mongo[settings.mongodb_db]
            await db.command("ping")
            yield Runtime(db, http, settings)
        finally:
            await mongo.close()


class Runtime:
    def __init__(self, db, http, settings):
        self.db, self.http, self.s = db, http, settings
        self.voyage = Voyage(http, settings)
        self.retriever = AtlasRetriever(db, self.voyage, settings)
        self.jev, self.llm = JevVerifier(http, settings), LLMVerifier(http, settings)
        self.cache, self.runs = VerifiedCache(db), MongoRuns(db, settings.grounding_alpha)

    def service(self, verifier="jev", cache=True, namespace="live", retriever=None):
        return GroundingService(
            self.db,
            retriever or self.retriever,
            getattr(self, verifier),
            self.cache,
            self.runs,
            self.s,
            cache,
            namespace,
        )
