"""Curated restaurant catalogue and preference-aware daily recommendations."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from app.models.schemas import RestaurantRecommendation


class RestaurantRepository:
    def __init__(self, path: Path | None = None) -> None:
        default_path = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "processed"
            / "graph_entities.json"
        )
        self.path = path or default_path
        self._restaurants: list[RestaurantRecommendation] | None = None

    def all(self) -> list[RestaurantRecommendation]:
        if self._restaurants is None:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._restaurants = [
                RestaurantRecommendation.model_validate(item)
                for item in payload.get("restaurants", [])
            ]
        return [restaurant.model_copy(deep=True) for restaurant in self._restaurants]

    def recommend(
        self,
        destination: str,
        *,
        dietary: list[str] | None = None,
        target_cost_for_two_inr: Decimal | None = None,
        excluded_ids: set[str] | None = None,
    ) -> RestaurantRecommendation | None:
        excluded = excluded_ids or set()
        candidates = [
            item
            for item in self.all()
            if item.destination.casefold() == destination.casefold()
            and item.id not in excluded
        ]
        if not candidates:
            return None

        requested = {item.casefold() for item in dietary or []}

        def dietary_match(item: RestaurantRecommendation) -> bool:
            available = " ".join(item.dietary).casefold()
            if "vegan" in requested:
                return "vegan" in available
            if "vegetarian" in requested:
                return "vegetarian" in available
            if "halal" in requested:
                return "halal" in available
            return True

        matched = [item for item in candidates if dietary_match(item)]
        pool = matched or candidates
        target = target_cost_for_two_inr or Decimal(900)
        return min(
            pool,
            key=lambda item: (
                abs(item.average_cost_for_two_inr - target),
                -(item.rating or 0),
                item.name.casefold(),
            ),
        )
