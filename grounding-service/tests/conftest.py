import asyncio
from types import SimpleNamespace

import mongomock
import pytest

from src.config import Settings
from src.models import Chunk, EvidenceBundle, Judgment, Usage, VerificationRequest
from src.util import digest


class AsyncCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def sort(self, *args):
        self.cursor = self.cursor.sort(*args)
        return self

    async def to_list(self, length=None):
        await asyncio.sleep(0)
        values = list(self.cursor)
        return values if length is None else values[:length]


class AsyncCollection:
    def __init__(self, collection):
        self.collection = collection

    def find(self, *args, **kwargs):
        return AsyncCursor(self.collection.find(*args, **kwargs))

    def __getattr__(self, name):
        async def call(*args, **kwargs):
            await asyncio.sleep(0)
            return getattr(self.collection, name)(*args, **kwargs)

        return call


@pytest.fixture
def db():
    database = mongomock.MongoClient().test
    return SimpleNamespace(
        **{
            name: AsyncCollection(database[name])
            for name in ["corpora", "source_chunks", "verified_claims", "grounding_runs"]
        }
    )


@pytest.fixture
def settings():
    return Settings(_env_file=None)


@pytest.fixture
def request_model():
    return VerificationRequest(run_id="test", claim_id="c1", claim="A fact.", scope={"corpus_id": "test"})


@pytest.fixture
def chunk():
    return Chunk(
        id="chunk1",
        text="A fact.",
        source_id="source",
        source_type="test",
        source_uri="test://source",
        page=1,
        version="v1",
        content_hash=digest("A fact."),
    )


class FakeRetriever:
    def __init__(self, chunk):
        self.chunk, self.calls = chunk, 0

    async def retrieve_evidence(self, claim, scope, revision, top_k=None):
        self.calls += 1
        await asyncio.sleep(0.002)
        return EvidenceBundle(claim=claim, chunks=[self.chunk], retrieval_latency_ms=2, retrieval_mode="fake")


class FakeVerifier:
    identity = "fixture-verifier-v1"

    def __init__(self):
        self.calls = self.active = self.peak = 0

    async def judge(self, request, chunks):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.003)
        self.active -= 1
        return Judgment(verdict="SUPPORTED", p_supported=0.8, p_contradicted=0.1, p_insufficient=0.1), Usage(
            provider="fake", operation="judge", cost=0.01, cost_kind="actual"
        )
