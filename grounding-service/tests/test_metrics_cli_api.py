import json

import pytest
from fastapi.testclient import TestClient

from benchmarks.metrics import cost_summary, metrics
from benchmarks.report import crossovers
from benchmarks.run import main
from src.api.main import app
from src.models import Judgment, VerificationRequest, VerificationResult


def result(label="SUPPORTED", probabilities=True):
    judgment = (
        Judgment(verdict="SUPPORTED", p_supported=0.8, p_contradicted=0.1, p_insufficient=0.1)
        if probabilities
        else Judgment.hard(label)
    )
    return VerificationResult(
        **judgment.model_dump(),
        run_id="r",
        claim_id="a",
        evidence_ids=[],
        corpus_revision="rev",
        verifier="test",
        total_latency_ms=100,
    ).model_dump(mode="json")


def test_metrics_failures_denominator_and_brier():
    fixtures = [{"claim_id": "a", "gold_label": "SUPPORTED"}, {"claim_id": "b", "gold_label": "CONTRADICTED"}]
    records = [{"claim_id": "a", "result": result()}, {"claim_id": "b", "error": "timeout"}]
    m = metrics(fixtures, records, 100, [])
    assert m["accuracy"] == m["coverage"] == 0.5
    assert m["confusion_matrix"]["CONTRADICTED"]["ERROR"] == 1
    assert m["brier_score"] == pytest.approx(0.06)
    assert m["brier_count"] == 1
    assert m["latency"]["total"]["p95_ms"] == 100


def test_one_hot_not_reported_as_probabilistic_brier():
    m = metrics(
        [{"claim_id": "a", "gold_label": "SUPPORTED"}],
        [{"claim_id": "a", "result": result(probabilities=False)}],
        100,
        [],
    )
    assert m["brier_score"] is None


def test_unknown_cost_not_zero_and_explicit_estimate(settings):
    calls = [
        {
            "provider": "voyage",
            "operation": "embeddings",
            "calls": 1,
            "input_tokens": 100,
            "output_tokens": None,
            "cost": None,
            "cost_kind": "unavailable",
        }
    ]
    assert cost_summary(calls)["total_cost"] is None
    s = settings.model_copy(update={"voyage_usd_per_million_tokens": 0.1})
    assert cost_summary(calls, s)["total_cost"] == pytest.approx(0.00001)
    assert cost_summary(calls, s)["cost_kind"] == "ESTIMATED"


def test_context_skip_never_declared_a_win():
    summary = [
        {
            "suite": "synthetic_5000",
            "corpus_size": 5000,
            "approach": "llm_posthoc",
            "phase": "cold",
            "status": "skipped_context_budget",
        }
    ]
    assert "no measured crossover" in crossovers(summary)[0]["conclusion"]


async def test_offline_cli_writes_honest_artifacts(tmp_path):
    assert (
        await main(
            ["--suite", "scale", "--sizes", "50", "500", "5000", "--offline", "--output", str(tmp_path)]
        )
        == 0
    )
    report = json.loads((tmp_path / "latest.json").read_text())
    assert report["status"] == "offline_dataset_validation_only"
    assert report["runs"] == report["summary"] == []
    assert [d["chunks"] for d in report["datasets"]] == [50, 500, 5000]
    assert (tmp_path / "latest.csv").exists() and (tmp_path / "latest.md").exists()


def test_request_scope_rejects_operators_and_invalid_importance():
    base = {"run_id": "r", "claim_id": "c", "claim": "x", "scope": {"corpus_id": "test"}}
    for change in [
        {"scope": {"$where": "bad"}},
        {"scope": {"corpus_id": {"$ne": None}}},
        {"importance": float("nan")},
        {"importance": -1},
    ]:
        with pytest.raises(ValueError):
            VerificationRequest(**{**base, **change})


def test_api_input_validation_without_external_calls():
    client = TestClient(app)
    response = client.post("/verify", json={"run_id": "r", "claim_id": "c", "claim": "test", "scope": {}})
    assert response.status_code == 422
    assert client.post("/verify/batch", json={"requests": []}).status_code == 422


def test_live_benchmark_requires_atlas(settings):
    from pydantic import SecretStr

    assert not settings.model_copy(
        update={"mongodb_uri": SecretStr("mongodb://localhost:27017")}
    ).is_atlas_uri()
    assert settings.model_copy(
        update={"mongodb_uri": SecretStr("mongodb+srv://user:pass@cluster.mongodb.net/")}
    ).is_atlas_uri()
