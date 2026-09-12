"""Normalize a user-owned JSON folder into TravelMind chunks and place records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import time
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.models.schemas import Citation, Place
from app.rag.ingestion.pipeline import ingest_file, write_jsonl


def topic_for(path: Path) -> str:
    name = path.stem.casefold()
    for marker, topic in (
        ("food", "food"),
        ("accommodation", "accommodation"),
        ("event", "event"),
        ("transit", "transport"),
        ("footfall", "crowd-seasonality"),
        ("vector", "travel-knowledge"),
    ):
        if marker in name:
            return topic
    return "attraction"


def location_for(path: Path) -> str:
    name = path.stem.casefold()
    if "chennai" in name:
        return "Chennai"
    if "mahabalipuram" in name or "mamallapuram" in name:
        return "Mamallapuram"
    if "puducherry" in name:
        return "Puducherry"
    return "Chennai-Mamallapuram-Puducherry"


def parse_clock(value: object, fallback: time) -> time:
    if isinstance(value, dict):
        value = value.get("open") or value.get("close")
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", str(value or ""))
    return time(int(match.group(1)), int(match.group(2))) if match else fallback


def categories(value: object) -> list[str]:
    parts = re.split(r"[/&,()]", str(value or "attraction"))
    return [part.strip().casefold() for part in parts if part.strip()]


def destination(payload: dict, path: Path) -> str:
    value = str(payload.get("destination") or payload.get("city") or location_for(path))
    folded = value.casefold()
    if "maha" in folded or "mamal" in folded:
        return "Mamallapuram"
    if "pudu" in folded or "pondi" in folded:
        return "Puducherry"
    return "Chennai" if "chennai" in folded else value


def iter_attractions(payload: dict) -> list[dict]:
    records: list[dict] = []
    if isinstance(payload.get("attractions"), list):
        records.extend(payload["attractions"])
    if payload.get("title") == "Master Attraction & Heritage Entity Dataset":
        records.extend(payload.get("items", []))
    return records


def place_from(record: dict, place_destination: str) -> Place | None:
    coordinates = record.get("geo_coordinates") or {}
    if "latitude" not in coordinates or "longitude" not in coordinates:
        return None
    fees = record.get("entry_fee_inr") or {}
    fee = fees.get("domestic", fees.get("entry", 0)) if isinstance(fees, dict) else 0
    hours = record.get("opening_hours") or {}
    opened = hours.get("open") if isinstance(hours, dict) else hours
    closed = hours.get("close") if isinstance(hours, dict) else hours
    category_values = categories(record.get("category"))
    citation = Citation(
        title="User-provided RAG dataset; verify before travel",
        publisher="User-provided dataset",
        reliability=0.4,
        is_live=False,
    )
    return Place(
        id=str(record.get("attraction_id") or record.get("place_id")),
        name=str(record.get("name")),
        destination=place_destination,
        categories=category_values,
        description=str(record.get("description") or "User-provided record; live details unknown."),
        latitude=float(coordinates["latitude"]),
        longitude=float(coordinates["longitude"]),
        visit_minutes=int(record.get("avg_visit_duration_mins") or 90),
        estimated_cost_inr=Decimal(str(fee or 0)),
        opening_time=parse_clock(opened, time(9, 0)),
        closing_time=parse_clock(closed, time(18, 0)),
        indoor=any("museum" in item for item in category_values),
        crowd_level=5,
        citations=[citation],
        live_status="unverified",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--chunks-output",
        type=Path,
        default=PROJECT_ROOT / "data" / "chunks" / "chunks.jsonl",
    )
    parser.add_argument(
        "--places-output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "places.json",
    )
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"RAG data directory not found: {source_dir}")

    chunks = []
    places: dict[str, Place] = {}
    for path in sorted(source_dir.glob("*.json")):
        metadata = {
            "source_id": f"user:{path.stem}",
            "title": path.stem.replace("_", " ").title(),
            "publisher": "User-provided dataset",
            "source_url": "",
            "location": location_for(path),
            "topic": topic_for(path),
            "license": "user-provided; original reuse terms require verification",
        }
        chunks.extend(ingest_file(path, metadata))
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        for record in iter_attractions(payload):
            place = place_from(record, destination(payload, path))
            if place:
                places[place.id] = place

    write_jsonl(chunks, args.chunks_output)
    args.places_output.parent.mkdir(parents=True, exist_ok=True)
    args.places_output.write_text(
        json.dumps(
            [place.model_dump(mode="json") for place in places.values()],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Imported {len(chunks)} chunks and {len(places)} geocoded places "
        f"from {source_dir}"
    )


if __name__ == "__main__":
    main()
