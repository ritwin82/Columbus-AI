"""Curated place catalogue repository."""

from __future__ import annotations

import json
from pathlib import Path

from app.models.schemas import Place


class CatalogueRepository:
    def __init__(self, path: Path | None = None) -> None:
        processed = Path(__file__).resolve().parents[3] / "data" / "processed"
        curated_path = processed / "places.json"
        default_path = curated_path if curated_path.exists() else processed / "demo_places.json"
        self.path = path or default_path
        self._places: list[Place] | None = None

    def all(self) -> list[Place]:
        if self._places is None:
            self._places = [Place.model_validate(item) for item in json.loads(self.path.read_text(encoding="utf-8"))]
        return [place.model_copy(deep=True) for place in self._places]

    def destinations(self, names: list[str]) -> list[Place]:
        requested = {name.casefold() for name in names}
        return [place for place in self.all() if place.destination.casefold() in requested]
