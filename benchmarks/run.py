import argparse
import asyncio
import hashlib
import json
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from benchmarks.generate_pdf_dataset import generate as generate_pdf
from benchmarks.generate_synthetic_dataset import generate as generate_synthetic
from benchmarks.generate_synthetic_dataset import oracle_label
from benchmarks.generate_technical_dataset import generate as generate_technical
from benchmarks.report import write_report
from benchmarks.runners import run_dataset
from scripts.ingest_pdf import ingest
from src.config import Settings
from src.ingestion import find_pdf, parse_pdf
from src.runtime import runtime
from src.technical_corpus import load_corpus
from src.util import elapsed


def datasets(args):
    if args.suite == "technical_http":
        chunks, _ = load_corpus()
        generated = generate_technical()
        stored = json.loads(Path("benchmarks/datasets/technical_http.json").read_text(encoding="utf-8"))
        if stored != generated:
            raise ValueError("Technical corpus or labels changed; review and regenerate the audited dataset")
        return [("http_rfc", chunks, stored["claims"])]
    if args.suite == "hackathon_pdf":
        pdf = Path(args.pdf) if args.pdf else find_pdf()
        fixture_path = Path("benchmarks/datasets/hackathon_pdf.json")
        fixture = (
            json.loads(fixture_path.read_text(encoding="utf-8"))
            if fixture_path.exists()
            else generate_pdf(pdf)
        )
        if fixture["source_sha256"] != hashlib.sha256(pdf.read_bytes()).hexdigest():
            raise ValueError("PDF changed since label audit; review and regenerate fixtures")
        return [("hackathon_pdf", parse_pdf(pdf), fixture["claims"])]
    result = []
    for size in args.sizes:
        chunks, claims = generate_synthetic(size)
        if any(oracle_label(c, chunks) != c["gold_label"] for c in claims):
            raise ValueError("Synthetic label oracle mismatch")
        result.append((f"synthetic_{size}", chunks, claims))
    return result


async def main(argv=None):
    p = argparse.ArgumentParser(
        description="Live Atlas benchmark; missing credentials produce a blocked report"
    )
    p.add_argument("--suite", choices=["hackathon_pdf", "technical_http", "scale"], default="technical_http")
    p.add_argument("--sizes", nargs="+", type=int, default=[50, 500, 5000])
    p.add_argument("--repetitions", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--pdf")
    p.add_argument(
        "--offline", action="store_true", help="Validate datasets only; NEVER simulate live metrics"
    )
    p.add_argument("--reranker", choices=["none", "voyage"])
    p.add_argument("--retrieval-mode", choices=["vector", "hybrid", "hybrid_reranked"])
    p.add_argument("--output", default="benchmarks/results")
    args = p.parse_args(argv)
    if args.repetitions < 1:
        p.error("--repetitions must be positive")
    overrides = {
        k: v for k, v in {"reranker": args.reranker, "retrieval_mode": args.retrieval_mode}.items() if v
    }
    s = Settings(**overrides)
    report = {
        "benchmark_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "preparing",
        "suite": args.suite,
        "missing": s.missing(baseline=True),
        "runs": [],
        "ingestion": [],
        "datasets": [],
        "seed": args.seed,
        "python": platform.python_version(),
        "implementation_sha256": hashlib.sha256(
            b"".join(
                str(path).encode() + path.read_bytes()
                for root in ["src", "benchmarks", "scripts"]
                for path in sorted(Path(root).rglob("*.py"))
            )
        ).hexdigest(),
        "config": s.model_dump(mode="json", exclude={"mongodb_uri", "openrouter_api_key", "voyage_api_key"}),
        "methodology": {
            "evidence": "Live retrieval each time; evidence pinned across judges within each repetition",
            "order": "Seeded shuffled approach order; cached cold pass immediately precedes warm",
            "atlas_llm_judge": "concurrency=1 serial control",
            "llm_parallel": "same judge at MAX_CONCURRENCY",
            "cost": "Includes query embeddings/reranking; ingestion reported separately; Atlas hosting excluded",
            "cache": "Separate namespace per approach/repetition; no cross-baseline cache reuse",
            "run_score_update": "atomic_update_pipeline_v1",
        },
    }
    exit_code = 0
    rt = None
    try:
        data = datasets(args)
        report["datasets"] = [
            {
                "corpus_id": name,
                "chunks": len(chunks),
                "claims": len(claims),
                "labels": {
                    label: sum(c["gold_label"] == label for c in claims)
                    for label in ["SUPPORTED", "CONTRADICTED", "INSUFFICIENT"]
                },
            }
            for name, chunks, claims in data
        ]
        if args.offline:
            report["status"] = "offline_dataset_validation_only"
        elif report["missing"]:
            report["status"], exit_code = "blocked_missing_credentials", 2
        elif not s.is_atlas_uri():
            report["status"], exit_code = "blocked_requires_atlas", 2
            report["error"] = "Live benchmark requires an Atlas mongodb.net URI from the emailed sandbox."
        else:
            async with runtime(s) as rt:
                report["status"] = "running"

                def checkpoint(row):
                    report["runs"].append(row)
                    report["all_api_calls"] = getattr(rt.http, "grounding_calls", [])
                    write_report(report, args.output)

                for name, chunks, claims in data:
                    tick = perf_counter()
                    corpus = await ingest(rt, chunks, name)
                    report["ingestion"].append({**corpus, "wall_ms": elapsed(tick)})
                    await run_dataset(
                        rt, claims, corpus, args.repetitions, args.seed, report["benchmark_id"], checkpoint
                    )
                    write_report(report, args.output)
            report["status"] = (
                "completed"
                if all(r["status"] in {"completed", "skipped_context_budget"} for r in report["runs"])
                else "completed_with_failures"
            )
            if report["status"] == "completed_with_failures":
                exit_code = 1
    except Exception as exc:  # noqa: BLE001 - always emit a report, including connection failures
        # Connection exceptions can contain hostnames; never serialize connection strings.
        report["status"], report["error"], exit_code = "failed", type(exc).__name__, 1
        if type(exc) is RuntimeError and str(exc).startswith(
            ("api.voyageai.com returned", "openrouter.ai returned")
        ):
            report["error"] = str(exc)
    finally:
        if rt is not None:
            report["all_api_calls"] = getattr(rt.http, "grounding_calls", [])
        write_report(report, args.output)
    print(f"{report['status']}: {args.output}/latest.md", flush=True)
    if report["missing"]:
        print("Missing: " + ", ".join(report["missing"]))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
