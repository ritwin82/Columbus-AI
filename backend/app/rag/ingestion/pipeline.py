"""Document extraction, normalization, chunking, and JSONL export."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(slots=True)
class SourceDocument:
    source_id: str
    title: str
    text: str
    source_url: str
    publisher: str
    location: str
    topic: str
    license: str
    retrieved_at: str


@dataclass(slots=True)
class DocumentChunk:
    id: str
    document_id: str
    title: str
    content: str
    source_url: str
    publisher: str
    location: str
    topic: str
    license: str
    retrieved_at: str


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_document(
    document: SourceDocument,
    *,
    target_words: int = 350,
    overlap_words: int = 50,
) -> list[DocumentChunk]:
    if target_words <= overlap_words:
        raise ValueError("target_words must be greater than overlap_words")
    words = clean_text(document.text).split()
    step = target_words - overlap_words
    chunks: list[DocumentChunk] = []
    for index, start in enumerate(range(0, len(words), step)):
        content = " ".join(words[start : start + target_words])
        if not content:
            continue
        digest = hashlib.sha256(
            f"{document.source_id}:{index}:{content}".encode()
        ).hexdigest()[:20]
        chunks.append(DocumentChunk(
            id=digest,
            document_id=document.source_id,
            title=document.title,
            content=content,
            source_url=document.source_url,
            publisher=document.publisher,
            location=document.location,
            topic=document.topic,
            license=document.license,
            retrieved_at=document.retrieved_at,
        ))
        if start + target_words >= len(words):
            break
    return chunks


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_html(path: Path) -> str:
    html = path.read_text(encoding="utf-8")
    try:
        import trafilatura

        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
        if extracted:
            return extracted
    except ImportError:
        pass

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "noscript"]):
            element.decompose()
        return soup.get_text("\n", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


def read_csv(path: Path) -> str:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return "\n".join("; ".join(f"{key}: {value}" for key, value in row.items()) for row in rows)


def read_pdf(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Install the ingestion extras to read PDF files") from exc
    with fitz.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def read_json(path: Path) -> str:
    """Turn arbitrary user-provided JSON into deterministic searchable text."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))

    def render(value: object, prefix: str = "") -> list[str]:
        if isinstance(value, dict):
            lines: list[str] = []
            for key, child in value.items():
                if key == "$schema":
                    continue
                label = f"{prefix} {key}".strip().replace("_", " ")
                lines.extend(render(child, label))
            return lines
        if isinstance(value, list):
            if all(not isinstance(item, (dict, list)) for item in value):
                return [f"{prefix}: {', '.join(str(item) for item in value)}"]
            lines = []
            for child in value:
                lines.extend(render(child, prefix))
            return lines
        return [f"{prefix}: {value}"]

    return "\n".join(render(payload))


def extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return read_text(path)
    if suffix in {".html", ".htm"}:
        return read_html(path)
    if suffix == ".csv":
        return read_csv(path)
    if suffix == ".json":
        return read_json(path)
    if suffix == ".pdf":
        return read_pdf(path)
    raise ValueError(f"Unsupported source type: {suffix}")


def ingest_file(path: Path, metadata: dict[str, str]) -> list[DocumentChunk]:
    document = SourceDocument(
        source_id=metadata.get("source_id") or path.stem,
        title=metadata.get("title") or path.stem.replace("-", " ").title(),
        text=extract(path),
        source_url=metadata.get("source_url", ""),
        publisher=metadata.get("publisher", "unknown"),
        location=metadata.get("location", "Tamil Nadu"),
        topic=metadata.get("topic", "travel"),
        license=metadata.get("license", "unknown"),
        retrieved_at=metadata.get("retrieved_at", datetime.now(UTC).date().isoformat()),
    )
    return chunk_document(document)


def write_jsonl(chunks: Iterable[DocumentChunk], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
