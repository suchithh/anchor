"""Section-aware RFC parsing; labels are never part of the ingested corpus."""

import hashlib
import json
import re
import textwrap
from pathlib import Path

from src.models import Chunk
from src.util import digest, normalize

RFC_ROOT = Path("benchmarks/datasets/http_rfc")
HEADING = re.compile(r"^(\d+(?:\.\d+)*\.)\s+(.+)$")


def parse_rfc(text, source, max_chars=1800):
    lines = text.splitlines()
    headings = [(i, HEADING.match(line)) for i, line in enumerate(lines) if HEADING.match(line)]
    chunks = []
    for position, (line_number, match) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        section = match[1].rstrip(".")
        title = match[2]
        cleaned = []
        for line in lines[line_number + 1 : end]:
            # Preserve paragraph boundaries while excluding print-edition running headers/footers.
            if re.search(r"\[Page \d+\]", line) or re.match(r"^RFC \d+\s{2,}", line):
                continue
            cleaned.append(line)
        paragraphs = [normalize(p) for p in re.split(r"\n\s*\n", "\n".join(cleaned)) if p.strip()]
        prefix = f"{source['source_id'].upper()} section {section}: {title}\n\n"
        parts = []
        current = []
        for paragraph in paragraphs:
            for block in textwrap.wrap(
                paragraph, width=max_chars, break_long_words=False, break_on_hyphens=False
            ):
                if current and len("\n\n".join([*current, block])) > max_chars:
                    parts.append("\n\n".join(current))
                    current = []
                current.append(block)
        if current:
            parts.append("\n\n".join(current))
        for part_number, part in enumerate(parts):
            content = prefix + part
            chunks.append(
                Chunk(
                    id=digest([source["source_id"], section, part_number, content]),
                    text=content,
                    source_id=source["source_id"],
                    source_type="rfc",
                    source_uri=source["source_uri"],
                    version=source["source_id"],
                    content_hash=digest(content),
                    metadata={
                        "section": section,
                        "heading": title,
                        "section_start_line": line_number + 1,
                        "section_end_line": end,
                        "part": part_number,
                        "document_sha256": source["sha256"],
                    },
                )
            )
    return chunks


def load_corpus(root=RFC_ROOT):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    chunks = []
    for source in manifest:
        body = (root / source["filename"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != source["sha256"]:
            raise ValueError(f"RFC snapshot hash mismatch: {source['source_id']}")
        chunks.extend(parse_rfc(body.decode("utf-8"), source))
    return chunks, manifest
