from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)
    mongodb_uri: SecretStr = SecretStr("")
    mongodb_db: str = "grounding_harness"
    mongodb_timeout_ms: int = Field(30000, ge=1000)
    openrouter_api_key: SecretStr = SecretStr("")
    voyage_api_key: SecretStr = SecretStr("")
    jev_model: str = "typesafe/jev-1.13"
    baseline_model: str = ""
    baseline_reasoning: bool = False
    voyage_model: str = "voyage-3.5-lite"
    embedding_dimensions: int = Field(1024, gt=0)
    vector_index_name: str = "grounding_vector"
    search_index_name: str = "grounding_text"
    top_k: int = Field(3, ge=1, le=50)
    max_concurrency: int = Field(8, ge=1, le=128)
    grounding_alpha: float = Field(0.8, ge=0, lt=1)
    retrieval_mode: Literal["vector", "hybrid", "hybrid_reranked"] = "vector"
    reranker: Literal["none", "voyage"] = "none"
    voyage_rerank_model: str = "rerank-2.5-lite"
    voyage_usd_per_million_tokens: float | None = Field(None, ge=0)
    voyage_rerank_usd_per_million_tokens: float | None = Field(None, ge=0)
    posthoc_max_input_bytes: int = Field(60000, gt=0)
    http_timeout_seconds: float = Field(90, gt=0)

    @field_validator("voyage_usd_per_million_tokens", "voyage_rerank_usd_per_million_tokens", mode="before")
    @classmethod
    def empty_price(cls, value):
        return None if value == "" else value

    def missing(self, baseline=False):
        names = ["mongodb_uri", "openrouter_api_key", "voyage_api_key"]
        if baseline:
            names.append("baseline_model")
        return [
            n.upper()
            for n in names
            if not (
                getattr(self, n).get_secret_value()
                if isinstance(getattr(self, n), SecretStr)
                else getattr(self, n)
            )
        ]

    def is_atlas_uri(self):
        """Prevent local MongoDB measurements from being mislabeled as live Atlas."""
        uri = urlsplit(self.mongodb_uri.get_secret_value())
        hosts = uri.netloc.rsplit("@", 1)[-1].split(",")
        return uri.scheme in {"mongodb", "mongodb+srv"} and all(
            host.split(":", 1)[0].lower().endswith(".mongodb.net") for host in hosts
        )
