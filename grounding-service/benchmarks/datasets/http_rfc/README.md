# HTTP standards corpus

Unmodified text editions downloaded from https://www.rfc-editor.org/:

- RFC 9110: HTTP Semantics (2022)
- RFC 9111: HTTP Caching (2022)
- RFC 9112: HTTP/1.1 (2022)
- RFC 5861: HTTP Cache-Control Extensions for Stale Content (2010)
- RFC 8246: HTTP Immutable Responses (2017)

Original copyright notices and licensing terms are preserved in each document. These documents
are source evidence, not authored by this project. `manifest.json` records source URLs, SHA-256 hashes,
retrieval timestamps, and byte sizes. Claims refer to these exact RFC editions; errata are not silently
applied. RFC 5861 is Informational, while the other four are Standards Track.

`python -m scripts.fetch_technical_corpus` downloads the sources. The section-aware parser currently
produces 582 evidence chunks. It excludes front matter/table-of-contents and print running headers,
retains section identifiers/headings, and groups paragraph text within an 1,800-character body budget.
Full source files remain unmodified. Benchmarks refuse mismatched source hashes or stale fixture IDs.

`python -m benchmarks.generate_technical_dataset` builds 36 manually audited claims, balanced across
SUPPORTED/CONTRADICTED/INSUFFICIENT, from the cited passages. Label generation never calls a model.
Gold labels and audit notes are stored separately and are never embedded or sent to the verifiers.

This technical corpus tests subtle directives, numeric boundaries, field precedence, validators,
and unknown runtime state. It is a curated challenge set, not a statistically representative sample
of all HTTP engineering work. Public RFCs may occur in model training data; success alone does not
prove the judge used retrieval. Use the synthetic/versioned suite to reduce that confound.
