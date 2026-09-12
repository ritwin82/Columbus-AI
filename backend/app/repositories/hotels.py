"""Static, replaceable hotel catalogue for the scoped prototype."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.models.schemas import Hotel


class HotelRepository:
    def __init__(self, path: Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[3] / "data" / "processed" / "hotels.json"
        self.path = path or default_path
        self._hotels: list[Hotel] | None = None

    def all(self) -> list[Hotel]:
        if self._hotels is None:
            self._hotels = [
                Hotel.model_validate(item)
                for item in json.loads(self.path.read_text(encoding="utf-8"))
            ]
        return [hotel.model_copy(deep=True) for hotel in self._hotels]

    def search(
        self,
        destination: str,
        *,
        max_price_inr: Decimal | None = None,
        price_tier: str | None = None,
        accessibility: list[str] | None = None,
        limit: int = 10,
    ) -> list[Hotel]:
        required_access = {item.casefold() for item in accessibility or []}
        matches = []
        for hotel in self.all():
            if hotel.destination.casefold() != destination.casefold():
                continue
            if max_price_inr is not None and hotel.estimated_price_from_inr > max_price_inr:
                continue
            if price_tier and hotel.price_tier.casefold() != price_tier.casefold():
                continue
            available_access = {item.casefold() for item in hotel.accessibility}
            if required_access and not required_access.issubset(available_access):
                continue
            matches.append(hotel)
        return sorted(
            matches,
            key=lambda hotel: (hotel.catalogue_rank, hotel.estimated_price_from_inr),
        )[:limit]

    def recommend(
        self,
        destination: str,
        target_price_inr: Decimal,
        accessibility: list[str] | None = None,
    ) -> Hotel | None:
        candidates = self.search(
            destination,
            accessibility=accessibility,
            limit=50,
        )
        if not candidates and accessibility:
            candidates = self.search(destination, limit=50)
        if not candidates:
            return None
        affordable = [
            hotel for hotel in candidates if hotel.estimated_price_from_inr <= target_price_inr
        ]
        pool = affordable or candidates
        return min(
            pool,
            key=lambda hotel: (
                abs(hotel.estimated_price_from_inr - target_price_inr),
                hotel.catalogue_rank,
            ),
        )
