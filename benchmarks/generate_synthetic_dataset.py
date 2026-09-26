import argparse
import json
from pathlib import Path

from src.models import Chunk
from src.util import digest


def generate(size):
    if not 2 <= size <= 5000:
        raise ValueError("size must be between 2 and 5000")
    corpus_id = f"synthetic_{size}"
    chunks = []
    for i in range(size):
        package, version = f"Package-{i // 2:04d}", f"v{i % 2 + 1}"
        facts = {
            "timeout_seconds": 10 + (i * 17) % 89,
            "auth_method": f"auth_{i:04d}()",
            "retry_limit": 1 + i % 7,
        }
        text = (
            f"{package} {version} technical reference. For {package} {version}, the timeout is "
            f"{facts['timeout_seconds']} seconds, the authentication method is {facts['auth_method']}, "
            f"and the retry limit is {facts['retry_limit']}. These settings apply only to {version}."
        )
        chunks.append(
            Chunk(
                id=f"synthetic-{i:05d}",
                text=text,
                source_id=package,
                source_type="synthetic",
                source_uri=f"synthetic://{package}/{version}",
                version=version,
                content_hash=digest(text),
                metadata={"facts": facts},
            )
        )
    claims = []
    for j in range(12):
        c = chunks[j * (size - 1) // 11]
        value = c.metadata["facts"]["timeout_seconds"]
        for label, field, proposed in [
            ("SUPPORTED", "timeout_seconds", value),
            ("CONTRADICTED", "timeout_seconds", value + 1),
            ("INSUFFICIENT", "compression_algorithm", "zstd"),
        ]:
            claim = (
                f"{c.source_id} {c.version} has a timeout of {proposed} seconds."
                if field == "timeout_seconds"
                else f"{c.source_id} {c.version} uses {proposed} compression."
            )
            claims.append(
                {
                    "claim_id": f"synthetic-{j:02d}-{label}",
                    "claim": claim,
                    "gold_label": label,
                    "gold_pages": [],
                    "gold_original_ids": [c.id] if label != "INSUFFICIENT" else [],
                    "scope": {"corpus_id": corpus_id},
                    "notes": "Deterministic template facts; compression unspecified.",
                    "oracle": {"chunk_id": c.id, "field": field, "value": proposed},
                }
            )
    # Same propositions with fresh IDs; exact repeats and paraphrases are distinguished.
    for row in claims[:3]:
        claims.append({**row, "claim_id": row["claim_id"] + "-repeat", "variant": "repeat"})
        text = (
            row["claim"]
            .replace("has a timeout of", "sets its timeout to")
            .replace("uses zstd compression", "compresses data with zstd")
        )
        claims.append(
            {**row, "claim_id": row["claim_id"] + "-paraphrase", "claim": text, "variant": "paraphrase"}
        )
    return chunks, claims


def oracle_label(row, chunks):
    c = next(c for c in chunks if c.id == row["oracle"]["chunk_id"])
    facts = c.metadata["facts"]
    field = row["oracle"]["field"]
    if field not in facts:
        return "INSUFFICIENT"
    return "SUPPORTED" if facts[field] == row["oracle"]["value"] else "CONTRADICTED"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size", type=int, default=500)
    p.add_argument("--output", default="benchmarks/datasets/synthetic.json")
    a = p.parse_args()
    chunks, claims = generate(a.size)
    target = Path(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"chunks": [c.model_dump() for c in chunks], "claims": claims}, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(chunks)} chunks and {len(claims)} claims")


if __name__ == "__main__":
    main()
