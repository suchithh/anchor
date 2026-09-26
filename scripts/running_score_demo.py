"""Zero-API replay of recorded judgments; demonstrates the running score, not measured timing."""

import argparse
import json
from pathlib import Path

from src.grounding.score import ewma


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="benchmarks/results/technical_http/latest.json")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    rows = [r for r in report["runs"] if r["approach"] == "atlas_jev" and r["status"] == "completed"]
    row = rows[-1]
    print("REPLAY: real saved judgments, input order. Not original completion order or live timing.")
    print("The live service persists this score after every completed verification.")
    print("\nClaim       Verdict          Support  Contradiction  Insufficient  Post-hoc review")
    previous = None
    timeline = []
    for index, record in enumerate(row["records"], 1):
        result = record["result"]
        probabilities = [result[k] for k in ["p_supported", "p_contradicted", "p_insufficient"]]
        previous = ewma(previous, probabilities, report["config"]["grounding_alpha"])
        posthoc = "waits for all claims" if index < len(row["records"]) else "can now review batch"
        print(
            f"{record['claim_id']:<11} {result['verdict']:<16} {previous[0]:7.1%} {previous[1]:13.1%} {previous[2]:13.1%}  {posthoc}"
        )
        timeline.append(
            {
                "claim_id": record["claim_id"],
                "verdict": result["verdict"],
                "support": previous[0],
                "contradiction": previous[1],
                "insufficient": previous[2],
            }
        )
    output = Path("benchmarks/results/running_score_replay.json")
    output.write_text(
        json.dumps(
            {
                "kind": "ILLUSTRATIVE_REPLAY_OF_MEASURED_JUDGMENTS",
                "source_benchmark_id": report["benchmark_id"],
                "source_run_id": row["records"][0]["result"]["run_id"],
                "order": "input order; not measured original completion order",
                "new_api_calls": 0,
                "timeline": timeline,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
