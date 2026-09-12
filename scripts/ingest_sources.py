"""Convert an approved local source file into provenance-preserving JSONL chunks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.rag.ingestion.pipeline import ingest_file, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--publisher", required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--location", default="Tamil Nadu")
    parser.add_argument("--topic", default="travel")
    parser.add_argument("--license", default="unknown")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "chunks" / "chunks.jsonl")
    args = parser.parse_args()

    source = args.source.resolve()
    raw_root = (PROJECT_ROOT / "data" / "raw").resolve()
    if raw_root not in source.parents:
        raise SystemExit(f"Source must be inside {raw_root}")
    chunks = ingest_file(source, {
        "source_id": args.source_id,
        "publisher": args.publisher,
        "source_url": args.source_url,
        "location": args.location,
        "topic": args.topic,
        "license": args.license,
    })
    write_jsonl(chunks, args.output)
    print(f"Wrote {len(chunks)} chunks to {args.output}")


if __name__ == "__main__":
    main()
