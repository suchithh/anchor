import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.generate_pdf_dataset import FACTS, generate
from benchmarks.generate_synthetic_dataset import generate as synthetic
from benchmarks.generate_synthetic_dataset import oracle_label
from src.ingestion import chunk_pages, find_pdf, parse_pdf, pdf_pages
from src.util import digest, normalize


def test_parse_local_pdf_and_hashes():
    pdf = find_pdf()
    pages, chunks = pdf_pages(pdf), parse_pdf(pdf)
    assert len(pages) == 8
    assert {c.page for c in chunks} == set(range(1, 9))
    assert len({c.id for c in chunks}) == len(chunks)
    for c in chunks:
        assert c.source_uri == pdf.name
        assert c.content_hash == digest(c.text)
        assert len(c.text) <= 1400
        assert normalize(c.text) in normalize(pages[c.page - 1])


def test_page_boundaries_and_sections():
    chunks = chunk_pages(["FIRST SECTION\nFact one.", "SECOND SECTION\nFact two."], "test.pdf")
    assert [c.page for c in chunks] == [1, 2]
    assert chunks[0].metadata["section"] == "FIRST SECTION"
    assert "Fact two" not in chunks[0].text


def test_pdf_labels_are_audited_and_unchanged():
    pdf = find_pdf()
    stored = json.loads(Path("benchmarks/datasets/hackathon_pdf.json").read_text(encoding="utf-8"))
    assert stored == generate(pdf)
    assert stored["source_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert Counter(c["gold_label"] for c in stored["claims"]) == {
        "SUPPORTED": 12,
        "CONTRADICTED": 12,
        "INSUFFICIENT": 12,
    }
    pages = pdf_pages(pdf)
    for page, quote, _, _ in FACTS:
        assert normalize(quote) in normalize(pages[page - 1])
    # These are absence claims, not contradictions. Prevent easy ground-truth regressions.
    labels = {c["claim"]: c["gold_label"] for c in stored["claims"]}
    assert labels["The maximum hackathon team size is six members."] == "CONTRADICTED"
    assert labels["OpenRouter credits expire exactly 30 days after the hackathon."] == "INSUFFICIENT"


@pytest.mark.parametrize("size", [50, 500, 5000])
def test_synthetic_oracle_and_reproducibility(size):
    chunks, rows = synthetic(size)
    assert len(chunks) == size
    assert len(rows) == 42
    assert Counter(r["gold_label"] for r in rows) == {"SUPPORTED": 14, "CONTRADICTED": 14, "INSUFFICIENT": 14}
    assert all(oracle_label(r, chunks) == r["gold_label"] for r in rows)
    assert synthetic(size) == (chunks, rows)
    assert {r.get("variant") for r in rows} >= {"repeat", "paraphrase"}
    assert chunks[0].source_id == chunks[1].source_id
    assert chunks[0].version != chunks[1].version
    assert chunks[0].metadata["facts"] != chunks[1].metadata["facts"]
