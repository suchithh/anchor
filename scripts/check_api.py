"""Live ASGI integration check: real Atlas/providers behind the three HTTP routes."""

import json
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.main import app


def main():
    fixtures = json.loads(Path("benchmarks/datasets/technical_http.json").read_text())["claims"]
    prefix = "api-smoke-" + uuid.uuid4().hex

    def request(index, run_id):
        fixture = fixtures[index]
        return {
            "run_id": run_id,
            "claim_id": fixture["claim_id"],
            "claim": fixture["claim"],
            "scope": fixture["scope"],
        }

    with TestClient(app) as client:
        first = client.post("/verify", json=request(0, prefix))
        first.raise_for_status()
        replay = client.post("/verify", json=request(0, prefix))
        replay.raise_for_status()
        assert replay.json()["deduplicated"]
        batch = client.post(
            "/verify/batch",
            json={"requests": [request(i, prefix + "-batch") for i in range(2)], "max_concurrency": 2},
        )
        batch.raise_for_status()
        results = batch.json()["results"]
        assert all("result" in item for item in results), results
        assert results[0]["result"]["cache_hit"]
        run = client.get("/runs/" + prefix + "-batch")
        run.raise_for_status()
        assert run.json()["num_claims"] == 2
        assert (
            abs(
                sum(run.json()[k] for k in ["grounding_score", "contradiction_score", "insufficient_score"])
                - 1
            )
            < 0.002
        )
        report = {
            "status": "passed",
            "transport": "ASGI TestClient; live Atlas and provider APIs",
            "verify": first.json(),
            "same_id_replay": replay.json(),
            "batch": batch.json(),
            "run": run.json(),
        }
    output = Path("benchmarks/results/api_smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Live API check passed: {output}")


if __name__ == "__main__":
    main()
