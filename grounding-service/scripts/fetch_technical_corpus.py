"""Download immutable RFC editions from their official publisher, preserving provenance."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

SOURCES = [9110, 9111, 9112, 5861, 8246]
ROOT = Path("benchmarks/datasets/http_rfc")


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = []
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for number in SOURCES:
            url = f"https://www.rfc-editor.org/rfc/rfc{number}.txt"
            response = await client.get(url)
            response.raise_for_status()
            body = response.content
            text = body.decode("utf-8")
            if f"{number}" not in text[:2000] or "<html" in text[:1000].lower():
                raise ValueError("Unexpected RFC document response")
            filename = f"rfc{number}.txt"
            (ROOT / filename).write_bytes(body)
            manifest.append(
                {
                    "source_id": f"rfc{number}",
                    "source_uri": url,
                    "filename": filename,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "bytes": len(body),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            print(f"Fetched RFC {number}: {len(body):,} bytes", flush=True)
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
