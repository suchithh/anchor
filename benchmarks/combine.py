"""Combine measured suites without inventing or averaging missing observations."""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.report import write_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--output", default="benchmarks/results")
    args = parser.parse_args()
    sources = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.reports]
    if len({s["benchmark_id"] for s in sources}) != len(sources):
        parser.error("A report was supplied more than once")
    comparable = ["baseline_model", "jev_model", "retrieval_mode", "reranker", "top_k", "voyage_model"]
    if any(any(s["config"][k] != sources[0]["config"][k] for k in comparable) for s in sources):
        parser.error("Different models or retrieval settings must be reported separately")
    if any(s["status"] not in {"completed", "completed_with_failures"} for s in sources):
        parser.error("Only finished experiments can be combined; retain interrupted diagnostics separately")
    report = {
        "benchmark_id": "combined-" + uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed"
        if all(s["status"] == "completed" for s in sources)
        else "completed_with_failures",
        "suite": "combined",
        "missing": [],
        "source_reports": [
            {k: v for k, v in s.items() if k not in {"runs", "summary", "all_api_calls", "crossover"}}
            for s in sources
        ],
        "methodology": "Source experiments executed separately. No cross-experiment randomization or statistical superiority claimed.",
        "runs": [r for s in sources for r in s["runs"]],
        "all_api_calls": [r for s in sources for r in s.get("all_api_calls", [])],
        "ingestion": [r for s in sources for r in s.get("ingestion", [])],
    }
    write_report(report, args.output)
    print(f"Wrote combined measured report: {args.output}/latest.md")


if __name__ == "__main__":
    main()
