"""End-to-end itinerary generation and targeted replanning service."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.core.config import Settings
from app.integrations.providers import DemoProvider, PlaceProvider, RouteProvider, WeatherProvider
from app.models.schemas import (
    Activity,
    Citation,
    Itinerary,
    ItineraryDay,
    ReplanRequest,
    TripRequest,
)
from app.optimization.planner import (
    build_day,
    calculate_budget,
    optimize_order,
    suitability_score,
    validate,
)
from app.repositories.catalog import CatalogueRepository
from app.repositories.hotels import HotelRepository
from app.repositories.state import TripRepository
from app.services.llm import ModelUnavailable, OllamaGateway

if TYPE_CHECKING:
    from app.services.knowledge import KnowledgeService


class TripNotFound(KeyError):
    pass


class TravelPlannerService:
    def __init__(
        self,
        *,
        settings: Settings,
        catalogue: CatalogueRepository,
        repository: TripRepository,
        places: PlaceProvider | None = None,
        routes: RouteProvider | None = None,
        weather: WeatherProvider | None = None,
        llm: OllamaGateway | None = None,
        knowledge: KnowledgeService | None = None,
        hotels: HotelRepository | None = None,
    ) -> None:
        self.settings = settings
        self.catalogue = catalogue
        self.repository = repository
        demo = DemoProvider(catalogue.all())
        self.places = places or demo
        self.routes = routes or demo
        self.weather = weather or demo
        self.llm = llm
        self.knowledge = knowledge
        self.hotels = hotels

    async def generate(self, request: TripRequest) -> Itinerary:
        itinerary = await self._build(request, version=1, locked={})
        self.repository.save_request(itinerary.trip_id, request)
        self.repository.save_preferences(request.user_id, request.preferences)
        self.repository.save_version(itinerary)
        return itinerary

    async def replan(self, trip_id: UUID, changes: ReplanRequest) -> Itinerary:
        request = self.repository.get_request(trip_id)
        previous = self.repository.get_version(trip_id)
        if not request or not previous:
            raise TripNotFound(str(trip_id))
        updates = request.model_dump()
        if changes.updated_budget_inr is not None:
            updates["budget_inr"] = changes.updated_budget_inr
        if changes.preference_changes:
            preferences = request.preferences.model_dump()
            preferences.update(changes.preference_changes)
            updates["preferences"] = preferences
        updated_request = TripRequest.model_validate(updates)
        lock_ids = set(changes.locked_activity_ids) | set(updated_request.locked_activity_ids)
        locked = {
            activity.id: activity.model_copy(update={"locked": True}, deep=True)
            for day in previous.days for activity in day.activities
            if activity.id in lock_ids or activity.locked
        }
        itinerary = await self._build(
            updated_request,
            trip_id=trip_id,
            version=previous.version + 1,
            locked=locked,
            change_reason=changes.reason,
        )
        self.repository.save_request(trip_id, updated_request)
        self.repository.save_preferences(updated_request.user_id, updated_request.preferences)
        self.repository.save_version(itinerary)
        return itinerary

    async def _build(
        self,
        request: TripRequest,
        *,
        version: int,
        locked: dict[UUID, Activity],
        trip_id: UUID | None = None,
        change_reason: str = "",
    ) -> Itinerary:
        dates = [request.start_date + timedelta(days=index) for index in range(request.days)]
        locked_by_date: dict = {}
        for activity in locked.values():
            locked_by_date.setdefault(activity.start_at.date(), []).append(activity)

        all_candidates = self.catalogue.destinations(request.destinations)
        knowledge_hits = []
        if self.knowledge:
            query = " ".join([*request.destinations, *request.preferences.interests])
            knowledge_hits = await self.knowledge.search(query, limit=20)
        days: list[ItineraryDay] = []
        forecasts = []
        for index, date_value in enumerate(dates):
            destination = request.destinations[index % len(request.destinations)]
            candidates = [p for p in all_candidates if p.destination.casefold() == destination.casefold()]
            graph_scores = (
                await self.knowledge.candidate_place_scores(
                    destination,
                    dietary=request.preferences.dietary,
                    accessibility=request.preferences.accessibility,
                    month=date_value.strftime("%B"),
                )
                if self.knowledge
                else {}
            )
            live_candidates = await self.places.search("tourist attraction", destination)
            merged = {place.id: place for place in candidates}
            for live_place in live_candidates:
                match = next(
                    (item for item in candidates if item.name.casefold() == live_place.name.casefold()),
                    None,
                )
                if match:
                    match.live_status = live_place.live_status
                    match.citations.extend(live_place.citations)
                    merged[match.id] = match
                else:
                    merged[live_place.id] = live_place
            candidates = list(merged.values())
            if not candidates:
                days.append(ItineraryDay(date=date_value))
                continue

            if index == 0:
                forecasts = await self.weather.forecast(candidates[0].latitude, candidates[0].longitude)
            matrix = await self.routes.matrix(candidates, request.preferences.travel_mode)
            scores = [suitability_score(place, request.preferences) for place in candidates]
            for place_index, place in enumerate(candidates):
                scores[place_index] += graph_scores.get(place.id, 0.0)
                matching_hits = [
                    hit for hit in knowledge_hits
                    if place.name.casefold() in f"{hit.title} {hit.content}".casefold()
                ]
                if matching_hits:
                    scores[place_index] += min(3, len(matching_hits))
                    known_sources = {
                        (citation.publisher, str(citation.source_url))
                        for citation in place.citations
                    }
                    for hit in matching_hits[:3]:
                        key = (hit.publisher, hit.source_url)
                        if key in known_sources:
                            continue
                        place.citations.append(Citation.model_validate({
                            "title": hit.title,
                            "publisher": hit.publisher,
                            "source_url": hit.source_url or None,
                            "reliability": (
                                0.4 if hit.publisher == "User-provided dataset" else 0.75
                            ),
                            "is_live": False,
                        }))
                        known_sources.add(key)
                if place.id in request.mandatory_place_ids:
                    scores[place_index] += 100
            max_places = {"relaxed": 2, "moderate": 3, "packed": 4}[request.preferences.pace.value]
            order = optimize_order(matrix, scores, max_places)
            day = build_day(
                date_value=date_value,
                places=candidates,
                matrix=matrix,
                order=order,
                mode=request.preferences.travel_mode,
            )
            locked_for_day = sorted(locked_by_date.get(date_value, []), key=lambda item: item.start_at)
            if locked_for_day:
                locked_ids = {activity.place.id for activity in locked_for_day}
                additions = [activity for activity in day.activities if activity.place.id not in locked_ids]
                for addition in additions:
                    if all(
                        addition.end_at <= fixed.start_at or addition.start_at >= fixed.end_at
                        for fixed in locked_for_day
                    ):
                        locked_for_day.append(addition)
                day.activities = sorted(locked_for_day, key=lambda item: item.start_at)
            days.append(day)

        food_per_person = max(
            Decimal(300),
            min(Decimal(900), request.budget_inr * Decimal("0.20") / request.travellers / request.days),
        ).quantize(Decimal(1))
        nights = max(0, request.days - 1)
        hotel_target = max(
            Decimal(1000),
            min(
                Decimal(12000),
                request.budget_inr * Decimal("0.35") / max(1, nights),
            ),
        ).quantize(Decimal(1))
        recommended_hotels = []
        if self.hotels and nights:
            overnight_destinations = [
                request.destinations[index % len(request.destinations)]
                for index in range(nights)
            ]
            for destination in dict.fromkeys(overnight_destinations):
                recommendation = self.hotels.recommend(
                    destination,
                    hotel_target,
                    request.preferences.accessibility,
                )
                if recommendation:
                    recommended_hotels.append(recommendation)
        hotel_per_night = (
            sum(
                (hotel.estimated_price_from_inr for hotel in recommended_hotels),
                Decimal(0),
            )
            / len(recommended_hotels)
            if recommended_hotels
            else hotel_target
        ).quantize(Decimal(1))
        budget = calculate_budget(
            days,
            limit=request.budget_inr,
            travellers=request.travellers,
            daily_food_per_person=food_per_person,
            accommodation_per_night=hotel_per_night,
        )
        violations = validate(days, budget, forecasts)
        citations = []
        seen = set()
        for day in days:
            for activity in day.activities:
                for citation in activity.place.citations:
                    key = (citation.publisher, str(citation.source_url))
                    if key not in seen:
                        seen.add(key)
                        citations.append(citation)
        confidence = min(0.95, 0.5 + len(citations) * 0.05)
        title = f"{request.days}-day {'–'.join(request.destinations)} itinerary"
        summary = self._template_summary(request, days, change_reason)
        if self.llm and self.settings.ai_models_enabled:
            try:
                generated = await self.llm.chat(
                    model=self.settings.planner_model,
                    system=(
                        "Write a concise itinerary summary using only the supplied structured facts. "
                        "Do not invent prices, opening hours, or places."
                    ),
                    prompt=f"Request: {request.model_dump_json()}\nDays: {[d.model_dump(mode='json') for d in days]}",
                )
                summary = str(generated)
            except ModelUnavailable:
                pass
        return Itinerary(
            trip_id=trip_id or uuid4(),
            version=version,
            title=title,
            summary=summary,
            days=days,
            recommended_hotels=recommended_hotels,
            budget=budget,
            citations=citations,
            violations=violations,
            negotiation_options=self._negotiation_options(violations),
            confidence=confidence,
        )

    @staticmethod
    def _template_summary(request: TripRequest, days: list[ItineraryDay], reason: str) -> str:
        count = sum(len(day.activities) for day in days)
        base = f"A {request.preferences.pace.value} itinerary with {count} scheduled activities."
        return f"{base} Replanned because: {reason}" if reason else base

    @staticmethod
    def _negotiation_options(violations) -> list[str]:
        codes = {item.code for item in violations if item.severity == "error"}
        options: list[str] = []
        if "budget" in codes:
            options.extend([
                "Reduce accommodation or meal price bands.",
                "Remove an unlocked paid activity.",
                "Increase the budget while preserving the current plan.",
            ])
        if "overlap" in codes or "closed" in codes:
            options.extend([
                "Move the affected activity to another day.",
                "Replace it with a nearby attraction that fits the available time window.",
            ])
        return options
