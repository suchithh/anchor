import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from src.models import Chunk
from src.util import digest


def pdf_pages(path):
    reader = PdfReader(path)
    pages = [unicodedata.normalize("NFKC", p.extract_text() or "") for p in reader.pages]
    if not any(p.strip() for p in pages):
        raise ValueError("PDF has no extractable text; OCR is not implemented")
    return pages


def chunk_pages(pages, filename, max_chars=1400):
    """Never cross pages; prefer headings/bullets, then sentence boundaries."""
    chunks = []
    for page, raw in enumerate(pages, 1):
        heading = None
        current = []

        def emit(current=current, page=page, section=None):
            if current:
                text = " ".join(current).strip()
                chunks.append(
                    Chunk(
                        id=digest([filename, page, len(chunks), text]),
                        text=text,
                        source_id=filename,
                        source_type="pdf",
                        source_uri=filename,
                        page=page,
                        version="pdf-v1",
                        content_hash=digest(text),
                        metadata={"section": section},
                    )
                )
                current.clear()

        for line in raw.splitlines():
            line = line.strip()
            if not line or line == str(page):
                continue
            is_heading = len(line) < 100 and line.isupper() and any(c.isalpha() for c in line)
            if is_heading or line.startswith("●"):
                emit(section=heading)
            if is_heading:
                heading = line
            # Long paragraphs break on sentences, with a word-boundary fallback.
            for part in re.split(r"(?<=[.!?])\s+", line):
                words = part.split()
                for word in words:
                    if sum(map(len, current)) + len(current) + len(word) > max_chars:
                        emit(section=heading)
                    current.append(word)
        emit(section=heading)
    return chunks


def parse_pdf(path):
    return chunk_pages(pdf_pages(path), Path(path).name)


def find_pdf():
    matches = [p for p in Path(".").glob("*.pdf") if "HARNESS" in p.name.upper()]
    if len(matches) != 1:
        raise ValueError("Pass --pdf: expected exactly one local HARNESS PDF")
    return matches[0]
