import math

from src.models import LABELS


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def cost_summary(calls, settings=None):
    calls = [dict(c) for c in calls]
    for call in calls:
        rate = None
        if settings and call["provider"] == "voyage":
            rate = (
                settings.voyage_rerank_usd_per_million_tokens
                if call["operation"] == "rerank"
                else settings.voyage_usd_per_million_tokens
            )
        if call["cost"] is None and rate is not None and call["input_tokens"] is not None:
            call["cost"] = call["input_tokens"] * rate / 1e6
            call["cost_kind"] = "ESTIMATED"
    complete = all(c["cost"] is not None for c in calls)
    providers = {}
    for provider in {c["provider"] for c in calls}:
        rows = [c for c in calls if c["provider"] == provider]
        providers[provider] = {
            "api_calls": sum(c["calls"] for c in rows),
            "input_tokens": sum(c["input_tokens"] for c in rows)
            if all(c["input_tokens"] is not None for c in rows)
            else None,
            "output_tokens": sum(c["output_tokens"] for c in rows)
            if all(c["output_tokens"] is not None for c in rows)
            else None,
            "cost": sum(c["cost"] for c in rows) if all(c["cost"] is not None for c in rows) else None,
            "known_cost_subtotal": sum(c["cost"] or 0 for c in rows),
            "cost_kind": "unavailable"
            if any(c["cost"] is None for c in rows)
            else ("ESTIMATED" if any(c["cost_kind"] == "ESTIMATED" for c in rows) else "actual"),
        }
    return {
        "api_calls": sum(c["calls"] for c in calls),
        "input_tokens": sum(c["input_tokens"] for c in calls)
        if all(c["input_tokens"] is not None for c in calls)
        else None,
        "output_tokens": sum(c["output_tokens"] for c in calls)
        if all(c["output_tokens"] is not None for c in calls)
        else None,
        "total_cost": sum(c["cost"] for c in calls) if complete else None,
        "known_cost_subtotal": sum(c["cost"] or 0 for c in calls),
        "cost_kind": "unavailable"
        if not complete
        else ("ESTIMATED" if any(c["cost_kind"] == "ESTIMATED" for c in calls) else "actual"),
        "providers": providers,
    }


def metrics(fixtures, records, batch_wall_ms, calls, settings=None, posthoc=False):
    successes = [r for r in records if "result" in r]
    gold = {f["claim_id"]: f["gold_label"] for f in fixtures}
    matrix = {label: {pred: 0 for pred in [*LABELS, "ERROR"]} for label in LABELS}
    for row in records:
        actual = gold[row["claim_id"]]
        predicted = row["result"]["verdict"] if "result" in row else "ERROR"
        matrix[actual][predicted] += 1
    n = len(fixtures)
    per_class = {}
    for label in LABELS:
        tp = matrix[label][label]
        predicted = sum(matrix[actual][label] for actual in LABELS)
        actual = sum(matrix[label].values())
        precision, recall = tp / predicted if predicted else 0, tp / actual if actual else 0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        }
    briers = []
    for row in successes:
        r = row["result"]
        if r["probability_kind"] != "model_distribution":
            continue
        p = [r["p_supported"], r["p_contradicted"], r["p_insufficient"]]
        briers.append(sum((v - int(label == gold[row["claim_id"]])) ** 2 for label, v in zip(LABELS, p)))
    latency = {}
    for name in ["cache_lookup", "retrieval", "reranker", "verifier", "persistence", "total"]:
        values = [r["result"][f"{name}_latency_ms"] for r in successes]
        latency[name] = {"p50_ms": percentile(values, 0.5), "p95_ms": percentile(values, 0.95)}
    costs = cost_summary(calls, settings)
    result = {
        "attempted": n,
        "completed": len(successes),
        "errors": n - len(successes),
        "coverage": len(successes) / n if n else 0,
        "accuracy": sum(matrix[k][k] for k in LABELS) / n if n else None,
        "macro_f1": sum(v["f1"] for v in per_class.values()) / 3,
        "confusion_matrix": matrix,
        "per_class": per_class,
        "brier_score": sum(briers) / len(briers) if briers else None,
        "brier_count": len(briers),
        "latency": latency,
        "batch_wall_ms": batch_wall_ms,
        "throughput_claims_per_second": len(successes) / (batch_wall_ms / 1000) if batch_wall_ms else None,
        "sum_individual_latency_ms": sum(r["result"]["total_latency_ms"] for r in successes),
        "async_overlap_ratio": None
        if posthoc or not batch_wall_ms
        else sum(r["result"]["total_latency_ms"] for r in successes) / batch_wall_ms,
        "cache_hit_rate": sum(r["result"]["cache_hit"] for r in successes) / n if n else 0,
        "verifier_calls_avoided": sum(r["result"]["cache_hit"] for r in successes),
        "avoided_verifier_cost_estimate": sum(r["result"]["avoided_verifier_cost"] or 0 for r in successes)
        if all(
            r["result"]["avoided_verifier_cost"] is not None for r in successes if r["result"]["cache_hit"]
        )
        else None,
        "cost": costs,
        "cost_per_1000_claims": costs["total_cost"] * 1000 / n
        if costs["total_cost"] is not None and n
        else None,
    }
    return result
