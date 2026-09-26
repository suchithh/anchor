import hashlib
import json
import unicodedata
from time import perf_counter


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def normalize(text):
    # Preserve case, punctuation and identifiers: case folding can change code semantics.
    return " ".join(unicodedata.normalize("NFC", text).split())


def elapsed(start):
    return (perf_counter() - start) * 1000
