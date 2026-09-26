from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Label(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"


LABELS = [x.value for x in Label]


class VerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    run_id: str = Field(min_length=1, max_length=200)
    claim_id: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=20000)
    context: str | None = Field(None, max_length=30000)
    scope: dict[str, Any]
    importance: float = Field(1, gt=0, le=100)

    @model_validator(mode="after")
    def check_scope(self):
        if not self.claim.strip():
            raise ValueError("claim cannot be blank")
        if not self.scope.get("corpus_id"):
            raise ValueError("scope.corpus_id is required")
        if set(self.scope) - {"corpus_id", "source_id", "version"}:
            raise ValueError("Supported scope keys: corpus_id, source_id, version")
        if any(not isinstance(v, str) or not v for v in self.scope.values()):
            raise ValueError("scope values must be nonempty strings")
        return self


class Chunk(BaseModel):
    id: str
    text: str
    source_id: str
    source_type: str
    source_uri: str
    page: int | None = None
    version: str
    content_hash: str
    metadata: dict = Field(default_factory=dict)


class Usage(BaseModel):
    provider: str
    operation: str
    calls: int = 1
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    cost_kind: str = "unavailable"
    model: str | None = None


class Judgment(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    verdict: Label
    p_supported: float = Field(ge=0, le=1)
    p_contradicted: float = Field(ge=0, le=1)
    p_insufficient: float = Field(ge=0, le=1)
    probability_kind: str = "model_distribution"

    @model_validator(mode="after")
    def distribution(self):
        if abs(sum(self.probabilities()) - 1) > 0.002:
            raise ValueError("probabilities must sum to one")
        if self.probabilities()[LABELS.index(self.verdict.value)] + 0.002 < max(self.probabilities()):
            raise ValueError("verdict disagrees with probabilities")
        return self

    def probabilities(self):
        return [self.p_supported, self.p_contradicted, self.p_insufficient]

    @classmethod
    def hard(cls, label):
        label = Label(label)
        return cls(
            verdict=label,
            p_supported=float(label == Label.SUPPORTED),
            p_contradicted=float(label == Label.CONTRADICTED),
            p_insufficient=float(label == Label.INSUFFICIENT),
            probability_kind="one_hot_label",
        )


class EvidenceBundle(BaseModel):
    claim: str
    chunks: list[Chunk]
    retrieval_latency_ms: float
    retrieval_mode: str
    reranker_latency_ms: float = 0
    pre_rerank_ids: list[str] = Field(default_factory=list)
    usage: list[Usage] = Field(default_factory=list)


class VerificationResult(Judgment):
    run_id: str
    claim_id: str
    evidence_ids: list[str]
    cache_lookup_latency_ms: float = 0
    retrieval_latency_ms: float = 0
    reranker_latency_ms: float = 0
    verifier_latency_ms: float = 0
    persistence_latency_ms: float = 0
    total_latency_ms: float = 0
    verifier_cost: float | None = None
    cache_hit: bool = False
    usage: list[Usage] = Field(default_factory=list)
    corpus_revision: str
    verifier: str
    deduplicated: bool = False
    avoided_verifier_cost: float | None = None
    avoided_cost_kind: str = "unavailable"
