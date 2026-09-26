from collections import Counter

from benchmarks.generate_technical_dataset import FACTS, generate
from src.technical_corpus import load_corpus, parse_rfc
from src.util import normalize


def test_rfc_snapshot_labels_and_evidence():
    chunks, manifest = load_corpus()
    assert len(manifest) == 5 and len(chunks) > 500
    assert len({c.id for c in chunks}) == len(chunks)
    data = generate()
    assert Counter(r["gold_label"] for r in data["claims"]) == {
        "SUPPORTED": 12,
        "CONTRADICTED": 12,
        "INSUFFICIENT": 12,
    }
    by_id = {c.id: c for c in chunks}
    for row in data["claims"]:
        if row["gold_label"] == "INSUFFICIENT":
            assert not row["gold_original_ids"] and row["notes"]
        else:
            assert row["gold_original_ids"]
            assert all(
                normalize(row["gold_quote"]) in normalize(by_id[key].text) for key in row["gold_original_ids"]
            )
    assert len(FACTS) == 12


def test_rfc_toc_and_page_artifacts_not_mistaken_for_sections():
    text = (
        "Table of Contents\n   1.  Intro\n\n1.  Intro\n\n   Normative first paragraph.\n\n"
        "Author Standards Track [Page 1]\n\f\nRFC 1234    Example    June 2022\n\n"
        "   Continued paragraph.\n\n1.1.  Detail\n\n   More evidence."
    )
    chunks = parse_rfc(text, {"source_id": "rfc1234", "source_uri": "test://rfc", "sha256": "test"})
    assert len(chunks) == 2
    assert chunks[0].metadata["section"] == "1"
    assert "Normative" in chunks[0].text and "Continued" in chunks[0].text
    assert "[Page" not in chunks[0].text and "June 2022" not in chunks[0].text
    assert chunks[1].metadata["section"] == "1.1"
