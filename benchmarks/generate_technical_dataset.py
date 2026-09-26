"""Manual, section-audited technical claims. Generate fixtures without any model calls."""

import json
from pathlib import Path

from src.technical_corpus import load_corpus
from src.util import normalize

FACTS = [
    (
        "rfc9111",
        "5.2.2.4",
        "without forwarding it for validation and receiving a successful response",
        "Under RFC 9111, an unqualified no-cache response directive requires successful validation before using the response to satisfy another request.",
        "Under RFC 9111, an unqualified no-cache response may be reused without validation whenever it is still fresh.",
    ),
    (
        "rfc9111",
        "5.3",
        "a recipient MUST ignore the Expires header field",
        "Under RFC 9111, when a response includes Cache-Control: max-age, the recipient must ignore its Expires header field.",
        "Under RFC 9111, Expires takes precedence over Cache-Control: max-age when both occur in the same response.",
    ),
    (
        "rfc9111",
        "5.2.2.7",
        "a shared cache MUST NOT store the response",
        "RFC 9111 prohibits a shared cache from storing a response carrying an unqualified private directive.",
        "RFC 9111 permits a shared cache to store a response carrying an unqualified private directive solely because its max-age is positive.",
    ),
    (
        "rfc9111",
        "5.2.2.2",
        "if a cache is disconnected, the cache MUST generate an error response rather than reuse the stale response",
        "Under RFC 9111, a disconnected cache must return an error instead of reusing a stale response carrying must-revalidate.",
        "Under RFC 9111, being disconnected allows a cache to ignore must-revalidate and serve the stale response.",
    ),
    (
        "rfc9111",
        "4.1",
        'a Vary header field value containing a member "*" always fails to match',
        'Under RFC 9111, a stored response whose Vary field contains "*" always fails to match.',
        "Under RFC 9111, Vary: * makes a stored response match every request for its target URI.",
    ),
    (
        "rfc9111",
        "1.2.2",
        "2147483648 (2^31) or the greatest positive integer it can conveniently represent",
        "RFC 9111 requires a cache to handle delta-seconds overflow as 2147483648 or the greatest positive integer it can conveniently represent.",
        "RFC 9111 requires overflowing delta-seconds values to wrap to negative integers.",
    ),
    (
        "rfc9110",
        "9.3.2",
        "the server MUST NOT send content in the response",
        "RFC 9110 forbids a server from sending content in a HEAD response.",
        "RFC 9110 requires a HEAD response to contain the same response body as GET.",
    ),
    (
        "rfc9110",
        "8.8.3.2",
        "two entity tags are equivalent if both are not weak",
        'Under RFC 9110 strong entity-tag comparison, W/"1" and "1" do not match.',
        'Under RFC 9110 strong entity-tag comparison, W/"1" and "1" match because their opaque tags are identical.',
    ),
    (
        "rfc9112",
        "6.3",
        "the Transfer-Encoding overrides the Content-Length",
        "RFC 9112 says Transfer-Encoding overrides Content-Length when a message contains both fields.",
        "RFC 9112 says Content-Length overrides Transfer-Encoding when a message contains both fields.",
    ),
    (
        "rfc9112",
        "7.1",
        "a chunk with a chunk-size of zero is received",
        "RFC 9112 completes chunked transfer coding with a zero-size chunk, an optional trailer section, and a final empty line.",
        "RFC 9112 says chunked transfer coding is complete immediately after any nonzero-size chunk, without a zero-size terminating chunk.",
    ),
    (
        "rfc5861",
        "3.1",
        "fresh for 600 seconds, and it may continue to be served stale for up to an additional 30 seconds",
        "RFC 5861's max-age=600, stale-while-revalidate=30 example allows an additional 30 seconds of stale serving while asynchronous validation is attempted.",
        "RFC 5861's max-age=600, stale-while-revalidate=30 example grants 630 additional seconds of stale serving after freshness expires.",
    ),
    (
        "rfc8246",
        "2",
        "The immutable extension only applies during the freshness lifetime",
        "RFC 8246 limits immutable to the freshness lifetime; stale responses should be revalidated normally.",
        "RFC 8246 says immutable permanently exempts a cached response from revalidation, including after it becomes stale.",
    ),
]

# Unknown runtime inputs are deliberately different from contradicted protocol rules.
UNKNOWN = [
    (
        "A stored response with max-age=600 is still fresh right now.",
        "No current age, Date, Age, receipt time, or clock values are supplied.",
    ),
    (
        "Two requests for /report are interchangeable under Vary: Accept-Language.",
        "The requests' Accept-Language field values are not supplied.",
    ),
    (
        "The cached representation's strong entity tag matches the origin's current strong entity tag.",
        "Neither the stored nor current origin entity-tag value is supplied.",
    ),
    (
        "The origin server has successfully validated our cached response during the last minute.",
        "No validation response or runtime timestamps are in the corpus.",
    ),
    (
        "Our cache's current response is within the stale-if-error=1200 allowance.",
        "No current staleness or error condition is supplied.",
    ),
    (
        "The response currently cached for /private carries an unqualified private directive.",
        "The actual response headers for /private are not supplied.",
    ),
    (
        "Our HTTP reverse proxy evicts cached objects using least-recently-used replacement.",
        "The RFCs specify protocol behavior, not this deployment's eviction policy.",
    ),
    (
        "Our application's origin generates entity tags using SHA-256 of the response body.",
        "No application implementation or tag-generation configuration is supplied.",
    ),
    (
        "Our cache has been configured with a 256 MiB storage capacity.",
        "The deployed cache's resource limits are not in the protocol specifications.",
    ),
    (
        "Our proxy can validate 10000 cached responses per second on its current hardware.",
        "No measurements, hardware description, or workload are supplied.",
    ),
    (
        "Our currently deployed intermediary supports the stale-while-revalidate extension.",
        "A specification of an extension does not establish deployment support.",
    ),
    (
        "The current origin response for /asset.js uses chunked transfer coding.",
        "No live response or application configuration is in the corpus.",
    ),
]


def generate():
    chunks, manifest = load_corpus()
    rows = []
    for source_id, section, quote, supported, contradicted in FACTS:
        evidence = [
            c
            for c in chunks
            if c.source_id == source_id
            and c.metadata["section"] == section
            and normalize(quote) in normalize(c.text)
        ]
        if not evidence:
            raise ValueError(f"Audited excerpt missing: {source_id} section {section}: {quote}")
        for label, claim in [("SUPPORTED", supported), ("CONTRADICTED", contradicted)]:
            rows.append(
                {
                    "claim": claim,
                    "gold_label": label,
                    "gold_pages": [],
                    "gold_original_ids": [c.id for c in evidence],
                    "gold_quote": quote,
                    "gold_sources": [
                        {
                            "source_id": source_id,
                            "section": section,
                            "url": f"https://www.rfc-editor.org/rfc/{source_id}.html#section-{section}",
                        }
                    ],
                    "notes": "Manually checked normative passage; preserve directive qualification, precedence, and RFC version.",
                }
            )
    for claim, note in UNKNOWN:
        rows.append(
            {
                "claim": claim,
                "gold_label": "INSUFFICIENT",
                "gold_pages": [],
                "gold_original_ids": [],
                "gold_sources": [],
                "notes": note,
            }
        )
    for i, row in enumerate(rows):
        row.update({"claim_id": f"http-{i:02d}", "scope": {"corpus_id": "http_rfc"}})
    return {
        "corpus_id": "http_rfc",
        "sources": [{"source_id": m["source_id"], "sha256": m["sha256"]} for m in manifest],
        "label_provenance": "Manual source-section audit; no model-generated gold labels",
        "claims": rows,
    }


def main():
    result = generate()
    Path("benchmarks/datasets/technical_http.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    chunks, _ = load_corpus()
    print(f"Wrote {len(result['claims'])} audited claims against {len(chunks)} RFC chunks")


if __name__ == "__main__":
    main()
