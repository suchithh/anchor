import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from benchmarks.metrics import percentile


def summarize(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["suite"], row["corpus_size"], row["approach"], row["phase"])].append(row)
    result = []
    for (suite, size, approach, phase), group in grouped.items():
        valid = [r for r in group if r.get("metrics") is not None]
        latencies = [
            record["result"]["total_latency_ms"]
            for r in valid
            for record in r["records"]
            if "result" in record
        ]
        complete_costs = valid and all(r["metrics"]["cost"]["total_cost"] is not None for r in valid)
        actual_openrouter = [
            r["metrics"]["cost"]["providers"].get("openrouter", {"cost": 0})["cost"] for r in valid
        ]
        result.append(
            {
                "suite": suite,
                "corpus_size": size,
                "approach": approach,
                "phase": phase,
                "status": "completed"
                if all(r["status"] == "completed" for r in group)
                else ",".join(sorted({r["status"] for r in group})),
                "repetitions": len(group),
                "accuracy": mean(r["metrics"]["accuracy"] for r in valid) if valid else None,
                "macro_f1": mean(r["metrics"]["macro_f1"] for r in valid) if valid else None,
                "p50_ms": percentile(latencies, 0.5),
                "p95_ms": percentile(latencies, 0.95),
                "mean_batch_wall_ms": mean(r["metrics"]["batch_wall_ms"] for r in valid) if valid else None,
                "mean_api_cost": mean(r["metrics"]["cost"]["total_cost"] for r in valid)
                if complete_costs
                else None,
                "mean_openrouter_cost": mean(actual_openrouter)
                if actual_openrouter and all(c is not None for c in actual_openrouter)
                else None,
                "cost_kind": ",".join(sorted({r["metrics"]["cost"]["cost_kind"] for r in valid}))
                or "unavailable",
            }
        )
    return sorted(result, key=lambda r: (r["corpus_size"], r["approach"], r["phase"]))


def crossovers(summary):
    rows = []
    for size in sorted({r["corpus_size"] for r in summary if r["suite"].startswith("synthetic_")}):
        subset = {r["approach"]: r for r in summary if r["corpus_size"] == size and r["phase"] == "cold"}
        posthoc, jev = subset.get("llm_posthoc"), subset.get("atlas_jev")
        row = {
            "corpus_size": size,
            "posthoc_status": posthoc["status"] if posthoc else "unavailable",
            "jev_status": jev["status"] if jev else "unavailable",
            "conclusion": "Not measured",
        }
        if posthoc and jev and posthoc["status"] == jev["status"] == "completed":
            faster = (
                "Atlas+Jev" if jev["mean_batch_wall_ms"] < posthoc["mean_batch_wall_ms"] else "Post-hoc LLM"
            )
            quality = f"accuracy Jev={jev['accuracy']:.3f}, post-hoc={posthoc['accuracy']:.3f}"
            row["conclusion"] = f"{faster} faster; {quality}"
            if jev["mean_api_cost"] is not None and posthoc["mean_api_cost"] is not None:
                cheaper = "Atlas+Jev" if jev["mean_api_cost"] < posthoc["mean_api_cost"] else "Post-hoc LLM"
                row["conclusion"] += f"; {cheaper} cheaper ({jev['cost_kind']}/{posthoc['cost_kind']})"
            else:
                row["conclusion"] += "; total API cost unavailable"
        elif posthoc and posthoc["status"] == "skipped_context_budget":
            row["conclusion"] = "Post-hoc exceeds configured input budget; no measured crossover"
        rows.append(row)
    return rows


def write_report(report, directory="benchmarks/results"):
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    report["summary"] = summarize(report.get("runs", []))
    report["crossover"] = crossovers(report["summary"])
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    (target / "latest.json").write_text(payload, encoding="utf-8")
    archive = target / "runs"
    archive.mkdir(exist_ok=True)
    (archive / f"{report['benchmark_id']}.json").write_text(payload, encoding="utf-8")
    fields = [
        "suite",
        "corpus_size",
        "approach",
        "phase",
        "status",
        "repetitions",
        "accuracy",
        "macro_f1",
        "p50_ms",
        "p95_ms",
        "mean_batch_wall_ms",
        "mean_api_cost",
        "mean_openrouter_cost",
        "cost_kind",
    ]
    with (target / "latest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(report["summary"])
    lines = [
        "# Grounding benchmark",
        "",
        f"Status: **{report['status']}**",
        "",
        "Missing configuration: " + (", ".join(report.get("missing", [])) or "none"),
        "",
        "| Approach / phase | Corpus | Accuracy | p50 ms | p95 ms | Mean batch ms | Mean API USD | OpenRouter USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if report.get("limitations"):
        lines[6:6] = ["Notes:", "", *["- " + note for note in report["limitations"]], ""]

    def fmt(value):
        return "unavailable" if value is None else f"{value:.6g}"

    for row in report["summary"]:
        lines.append(
            f"| {row['approach']} / {row['phase']} ({row['status']}) | {row['corpus_size']} | "
            + " | ".join(
                fmt(row[k])
                + (" ESTIMATED" if k == "mean_api_cost" and "ESTIMATED" in row["cost_kind"] else "")
                for k in [
                    "accuracy",
                    "p50_ms",
                    "p95_ms",
                    "mean_batch_wall_ms",
                    "mean_api_cost",
                    "mean_openrouter_cost",
                ]
            )
            + " |"
        )
    if not report["summary"]:
        lines += [
            "",
            "No live measurements. Offline dataset validation does not measure model quality, cost, or latency.",
        ]
    lines += ["", "| Corpus size | Post-hoc LLM | Atlas+Jev | Winner / tradeoff |", "|---:|---|---|---|"]
    for row in report["crossover"]:
        lines.append(
            f"| {row['corpus_size']} | {row['posthoc_status']} | {row['jev_status']} | {row['conclusion']} |"
        )
    lines += [
        "",
        "No cost/latency winner or crossover can be claimed without completed live measurements.",
        "",
        "Per-run raw results, failures, probabilities, timings, evidence IDs, usage, and ingestion overhead are in latest.json.",
        "API totals exclude Atlas hosting. Unknown Voyage prices remain unavailable. Free credits are not a zero marginal list price.",
        "LLM probabilities are one-hot labels for score compatibility; their Brier score is unavailable.",
        "p50/p95 measure service time; batch wall time includes concurrency queueing. Post-hoc claims share a completion time.",
        "Grounding uses completion-order EWMA. These small, curated datasets cannot establish statistical superiority.",
        "",
    ]
    if report.get("error"):
        lines += ["Run error: " + report["error"], ""]
    (target / "latest.md").write_text("\n".join(lines), encoding="utf-8")
