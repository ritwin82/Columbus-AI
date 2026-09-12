"""Conservatively collect public official tourism pages for the RAG corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.rag.ingestion.pipeline import SourceDocument, chunk_document, write_jsonl

USER_AGENT = "TravelMindAI-Academic-RAG/1.0 (+local student project)"
SEEDS = [
    ("https://www.incredibleindia.gov.in/", "Incredible India", "India", "travel"),
    ("https://www.tamilnadutourism.tn.gov.in/", "Tamil Nadu Tourism", "Tamil Nadu", "travel"),
    ("https://chennai.nic.in/tourism/", "Chennai District", "Chennai", "attraction"),
    ("https://chengalpattu.nic.in/tourist-place/mamallapuram/", "Chengalpattu District", "Mamallapuram", "attraction"),
    ("https://tourism.py.gov.in/", "Puducherry Tourism", "Puducherry", "travel"),
    ("https://puducherry-dt.gov.in/tourist-places/", "Puducherry District", "Puducherry", "attraction"),
    ("https://asi.nic.in/", "Archaeological Survey of India", "India", "heritage"),
    ("https://www.incredibleindia.gov.in/en/tamil-nadu/mamallapuram", "Incredible India", "Mamallapuram", "attraction"),
    ("https://www.incredibleindia.gov.in/en/puducherry", "Incredible India", "Puducherry", "attraction"),
    ("https://data.tourism.gov.in/", "Ministry of Tourism", "India", "statistics"),
    ("https://www.data.gov.in/", "Open Government Data Platform India", "India", "open-data"),
    ("https://tn.data.gov.in/", "Tamil Nadu Open Data", "Tamil Nadu", "open-data"),
]
LINK_TERMS = {
    "tourism", "tourist", "place", "attraction", "heritage", "museum", "temple",
    "beach", "chennai", "mamallapuram", "mahabalipuram", "puducherry", "event",
}
EXCLUDED_LINK_TERMS = {
    "election", "notification", "tender", "notice", "gallery", "contact",
    "map-of-district", "press-release", "recruitment",
}


def canonical(url: str) -> str:
    clean, _ = urldefrag(url)
    parsed = urlparse(clean)
    path = parsed.path or "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def same_host(left: str, right: str) -> bool:
    a = urlparse(left).hostname or ""
    b = urlparse(right).hostname or ""
    return a.removeprefix("www.") == b.removeprefix("www.")


def robots_for(client: httpx.Client, url: str) -> RobotFileParser | None:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = client.get(robots_url)
    except httpx.HTTPError:
        return None
    if response.status_code == 404:
        parser = RobotFileParser()
        parser.parse([])
        return parser
    if not response.is_success:
        return None
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser


def extract_text(html: str) -> str:
    try:
        import trafilatura

        text = trafilatura.extract(
            html, include_comments=False, include_tables=True, favor_precision=True
        )
        if text:
            return text
    except ImportError:
        pass
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "noscript"]):
        element.decompose()
    return soup.get_text("\n", strip=True)


def relevant_links(page_url: str, html: str) -> list[str]:
    links: set[str] = set()
    for anchor in BeautifulSoup(html, "html.parser").find_all("a", href=True):
        url = canonical(urljoin(page_url, anchor["href"]))
        parsed = urlparse(url)
        path_text = parsed.path.casefold()
        anchor_text = anchor.get_text(" ", strip=True).casefold()
        relevant = any(term in path_text for term in LINK_TERMS) or (
            path_text not in {"", "/"} and any(term in anchor_text for term in LINK_TERMS)
        )
        excluded = any(term in path_text for term in EXCLUDED_LINK_TERMS)
        if parsed.scheme == "https" and same_host(page_url, url) and relevant and not excluded:
            links.add(url)
    return sorted(links)


def existing_chunks(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return {
        item["id"]: item
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and (item := json.loads(line))
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages-per-site", type=int, default=3)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "data" / "chunks" / "chunks.jsonl"
    )
    args = parser.parse_args()
    raw_dir = PROJECT_ROOT / "data" / "raw" / "web"
    manifest_path = PROJECT_ROOT / "data" / "sources" / "crawl_manifest.jsonl"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    fetched_per_host: defaultdict[str, int] = defaultdict(int)
    robots_cache: dict[str, RobotFileParser | None] = {}
    visited: set[str] = set()
    queue = deque((canonical(url), publisher, location, topic, 0) for url, publisher, location, topic in SEEDS)
    new_chunks = []
    manifest = []

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True
    ) as client:
        while queue:
            url, publisher, location, topic, depth = queue.popleft()
            host = urlparse(url).hostname or ""
            if url in visited or fetched_per_host[host] >= args.max_pages_per_site:
                continue
            visited.add(url)
            if host not in robots_cache:
                robots_cache[host] = robots_for(client, url)
            robots = robots_cache[host]
            if robots is None or not robots.can_fetch(USER_AGENT, url):
                manifest.append({"url": url, "status": "skipped-robots-unknown-or-denied"})
                continue
            try:
                response = client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type or len(response.content) > 5_000_000:
                    manifest.append({"url": url, "status": "skipped-content-type-or-size"})
                    continue
            except httpx.HTTPError as exc:
                manifest.append({"url": url, "status": f"failed:{type(exc).__name__}"})
                continue

            fetched_per_host[host] += 1
            final_url = canonical(str(response.url))
            if not same_host(url, final_url):
                manifest.append({"url": url, "status": "skipped-cross-host-redirect"})
                continue
            digest = hashlib.sha256(final_url.encode()).hexdigest()[:20]
            snapshot = raw_dir / f"{digest}.html"
            snapshot.write_text(response.text, encoding="utf-8")
            soup = BeautifulSoup(response.text, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else final_url
            extracted_text = extract_text(response.text)
            if len(extracted_text.split()) < 80:
                manifest.append({"url": final_url, "status": "skipped-insufficient-text"})
                continue
            document = SourceDocument(
                source_id=f"web:{digest}",
                title=title,
                text=extracted_text,
                source_url=final_url,
                publisher=publisher,
                location=location,
                topic=topic,
                license="official public page; reuse terms require verification",
                retrieved_at=datetime.now(UTC).date().isoformat(),
            )
            page_chunks = chunk_document(document)
            new_chunks.extend(page_chunks)
            manifest.append(
                {
                    "url": final_url,
                    "status": "collected",
                    "publisher": publisher,
                    "retrieved_at": document.retrieved_at,
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "chunks": len(page_chunks),
                    "snapshot": str(snapshot.relative_to(PROJECT_ROOT)),
                }
            )
            if depth == 0:
                for link in relevant_links(final_url, response.text):
                    queue.append((link, publisher, location, topic, 1))
            time.sleep(max(0.0, args.delay_seconds))

    combined = existing_chunks(args.output)
    combined.update({chunk.id: asdict(chunk) for chunk in new_chunks})
    from app.rag.ingestion.pipeline import DocumentChunk

    write_jsonl((DocumentChunk(**item) for item in combined.values()), args.output)
    with manifest_path.open("w", encoding="utf-8") as handle:
        for item in manifest:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    collected = sum(item["status"] == "collected" for item in manifest)
    print(f"Collected {collected} pages, added {len(new_chunks)} chunks; see {manifest_path}")


if __name__ == "__main__":
    main()
