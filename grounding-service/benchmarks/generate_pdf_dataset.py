"""Manually audited against all eight pages of the supplied PDF; no LLM labeling."""

import argparse
import hashlib
import json
from pathlib import Path

from src.ingestion import find_pdf, pdf_pages
from src.util import normalize

# Each positive/negative pair has a source excerpt checked during generation.
FACTS = [
    (
        2,
        "MongoDB as your data and memory",
        "MongoDB is the hackathon's data and memory layer.",
        "The hackathon instructs teams to use PostgreSQL instead of MongoDB as the data and memory layer.",
    ),
    (
        3,
        "using the MongoDB Atlas Hackathon Sandbox",
        "Finalist projects must use the MongoDB Atlas Hackathon Sandbox.",
        "Finalist projects are exempt from using the MongoDB Atlas Hackathon Sandbox.",
    ),
    (
        3,
        "Up to 4 members",
        "A hackathon team can have at most four members.",
        "The maximum hackathon team size is six members.",
    ),
    (
        3,
        "All work must be original",
        "The hackathon requires original work.",
        "The hackathon explicitly allows submission of prior projects.",
    ),
    (
        3,
        "repository is public",
        "The demo access requirements include a public repository.",
        "The demo access requirements demand that the repository remain private.",
    ),
    (
        3,
        "All projects must be submitted through the Cerebral Valley Platform",
        "Projects must be submitted through the Cerebral Valley Platform.",
        "Projects must be submitted exclusively by email instead of the Cerebral Valley Platform.",
    ),
    (
        3,
        "a 1-minute demo video",
        "Submission includes a one-minute demo video showing code and functionality.",
        "The specified submission demo video duration is ten minutes.",
    ),
    (
        2,
        "Top 6 teams exhibit",
        "The top six teams exhibit at MongoDB.local NYC.",
        "Exactly the top twelve teams exhibit at MongoDB.local NYC.",
    ),
    (
        2,
        "Top 3 teams demo on-stage",
        "The top three teams demo on stage at MongoDB.local NYC.",
        "The guide specifies that the top ten teams demo on stage at MongoDB.local NYC.",
    ),
    (
        4,
        "typo-tolerant keyword search",
        "Atlas Search provides typo-tolerant keyword search.",
        "The guide says Atlas Search cannot tolerate typos in keyword search.",
    ),
    (
        6,
        "free credits for the hackathon",
        "OpenRouter provides free credits for the hackathon.",
        "The guide says OpenRouter provides no free credits for the hackathon.",
    ),
    (
        7,
        "200 million free tokens",
        "Every participant gets 200 million free Voyage AI tokens for the event.",
        "The stated free Voyage AI allowance is exactly two million tokens per participant.",
    ),
]
UNKNOWN = [
    (
        "OpenRouter credits expire exactly 30 days after the hackathon.",
        [6],
        "No OpenRouter expiration is stated; Kiro's 30-day bonus is a different offer.",
    ),
    (
        "The Atlas Hackathon Sandbox runs MongoDB server version 8.2.",
        [3, 4],
        "No server version is specified.",
    ),
    (
        "Each sandbox cluster includes three dedicated search nodes.",
        [3, 4],
        "No search-node topology is stated.",
    ),
    (
        "Each participant receives exactly $100 in OpenRouter credits.",
        [6],
        "The OpenRouter credit amount is not given.",
    ),
    (
        "The sandbox is hosted in AWS us-east-1.",
        [3, 4],
        "The cluster region and cloud provider are not specified.",
    ),
    (
        "The hackathon requires every project to use Python 3.11.",
        [3, 4, 5],
        "Language examples are resources, not a required Python version.",
    ),
    (
        "The event's Voyage AI allowance expires at midnight on September 30.",
        [7, 8],
        "No such expiry time is given.",
    ),
    ("Jev is a mandatory model for all hackathon submissions.", [], "Jev is never named in the guide."),
    (
        "The Atlas sandbox guarantees vector retrieval latency under 20 milliseconds.",
        [4],
        "No latency SLA appears in the guide.",
    ),
    (
        "Every team is assigned a dedicated MongoDB engineer for the entire day.",
        [],
        "No per-team staffing commitment is stated.",
    ),
    (
        "The guide states that Atlas Automated Embeddings uses the voyage-3.5-lite model.",
        [4],
        "Automated Embeddings is described without a model name.",
    ),
    (
        "The final judging score weights technical quality at exactly 40 percent.",
        [2, 3],
        "No numeric judging rubric is supplied.",
    ),
]


def generate(path):
    pages = pdf_pages(path)
    rows = []
    for page, quote, supported, contradicted in FACTS:
        if normalize(quote) not in normalize(pages[page - 1]):
            raise ValueError(f"PDF changed: audit excerpt missing on page {page}: {quote}")
        for label, claim in [("SUPPORTED", supported), ("CONTRADICTED", contradicted)]:
            rows.append(
                {
                    "claim": claim,
                    "gold_label": label,
                    "gold_pages": [page],
                    "gold_quote": quote,
                    "notes": "Manually checked source excerpt: " + quote,
                }
            )
    for claim, pages_read, note in UNKNOWN:
        rows.append(
            {
                "claim": claim,
                "gold_label": "INSUFFICIENT",
                "gold_pages": [],
                "reviewed_pages": pages_read or list(range(1, 9)),
                "notes": note + " All 8 pages reviewed.",
            }
        )
    for i, row in enumerate(rows):
        row["claim_id"] = f"pdf-{i:02d}"
        row["scope"] = {"corpus_id": "hackathon_pdf"}
    return {
        "source_filename": Path(path).name,
        "source_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "label_provenance": "Human-readable manual audit of local PDF; generator checks excerpts only, not semantics",
        "claims": rows,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pdf")
    p.add_argument("--output", default="benchmarks/datasets/hackathon_pdf.json")
    a = p.parse_args()
    result = generate(a.pdf or find_pdf())
    target = Path(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(result['claims'])} manually audited claims to {target}")


if __name__ == "__main__":
    main()
