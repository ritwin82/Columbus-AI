"""Provider-independent domain and API schemas."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator


class Pace(StrEnum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    PACKED = "packed"


class TravelMode(StrEnum):
    WALK = "walk"
    TRANSIT = "transit"
    DRIVE = "drive"
    TWO_WHEELER = "two_wheeler"


class Preferences(BaseModel):
    interests: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)
    accessibility: list[str] = Field(default_factory=list)
    excluded_categories: list[str] = Field(default_factory=list)
    pace: Pace = Pace.MODERATE
    travel_mode: TravelMode = TravelMode.DRIVE
    crowd_tolerance: int = Field(default=5, ge=1, le=10)
    preferred_language: str = "en"


class TripRequest(BaseModel):
    user_id: str = "demo-user"
    origin: str
    destinations: list[str] = Field(min_length=1)
    start_date: date
    days: int = Field(ge=1, le=5)
    travellers: int = Field(default=1, ge=1, le=20)
    budget_inr: Decimal = Field(gt=0)
    preferences: Preferences = Field(default_factory=Preferences)
    mandatory_place_ids: list[str] = Field(default_factory=list)
    locked_activity_ids: list[UUID] = Field(default_factory=list)


class Citation(BaseModel):
    title: str
    publisher: str
    source_url: HttpUrl | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_verified_at: date | None = None
    reliability: float = Field(default=0.5, ge=0, le=1)
    is_live: bool = False


class Place(BaseModel):
    id: str
    name: str
    destination: str
    categories: list[str]
    description: str = ""
    latitude: float
    longitude: float
    visit_minutes: int = Field(default=90, ge=15, le=720)
    estimated_cost_inr: Decimal = Field(default=Decimal(0), ge=0)
    opening_time: time = time(9, 0)
    closing_time: time = time(18, 0)
    indoor: bool = False
    dietary: list[str] = Field(default_factory=list)
    accessibility: list[str] = Field(default_factory=list)
    crowd_level: int = Field(default=5, ge=1, le=10)
    rating: float | None = Field(default=None, ge=0, le=5)
    user_rating_count: int | None = Field(default=None, ge=0)
    rating_source: str = "unavailable"
    citations: list[Citation] = Field(default_factory=list)
    live_status: str = "unknown"


class Hotel(BaseModel):
    id: str
    name: str
    destination: str
    area: str
    accommodation_type: str
    price_tier: str
    estimated_price_from_inr: Decimal = Field(ge=0)
    estimated_price_to_inr: Decimal = Field(ge=0)
    amenities: list[str] = Field(default_factory=list)
    accessibility: list[str] = Field(default_factory=list)
    catalogue_rank: int = Field(ge=1)
    source_note: str = "Curated prototype record; verify directly before booking."
    last_verified_at: date | None = None

    @model_validator(mode="after")
    def validate_price_range(self) -> Hotel:
        if self.estimated_price_to_inr < self.estimated_price_from_inr:
            raise ValueError("hotel maximum price must be greater than or equal to minimum")
        return self


class RouteLeg(BaseModel):
    origin_id: str
    destination_id: str
    duration_minutes: int = Field(ge=0)
    distance_km: float = Field(ge=0)
    mode: TravelMode
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WeatherWindow(BaseModel):
    at: datetime
    condition: str
    temperature_c: float
    rain_probability: float = Field(ge=0, le=1)
    wind_kph: float = Field(default=0, ge=0)
    source: str


class Activity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    place: Place
    start_at: datetime
    end_at: datetime
    route_from_previous: RouteLeg | None = None
    estimated_cost_inr: Decimal = Field(default=Decimal(0), ge=0)
    locked: bool = False
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_interval(self) -> Activity:
        if self.end_at <= self.start_at:
            raise ValueError("activity end time must be after start time")
        return self


class RestaurantRecommendation(BaseModel):
    id: str
    name: str
    destination: str
    area: str
    cuisines: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)
    average_cost_for_two_inr: Decimal = Field(ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    rating_source: str = "curated_snapshot"
    source_note: str = "Approximate catalogue data; verify current price, rating, and availability."

    @property
    def estimated_meal_cost_per_person_inr(self) -> Decimal:
        return (self.average_cost_for_two_inr / Decimal(2)).quantize(Decimal(1))


class ItineraryDay(BaseModel):
    date: date
    activities: list[Activity] = Field(default_factory=list)
    restaurant: RestaurantRecommendation | None = None


class BudgetBreakdown(BaseModel):
    attractions: Decimal = Decimal(0)
    food: Decimal = Decimal(0)
    transport: Decimal = Decimal(0)
    accommodation: Decimal = Decimal(0)
    contingency: Decimal = Decimal(0)
    total: Decimal = Decimal(0)
    limit: Decimal = Decimal(0)


class ValidationViolation(BaseModel):
    code: str
    message: str
    day: date | None = None
    activity_id: UUID | None = None
    severity: str = "error"


class Itinerary(BaseModel):
    trip_id: UUID = Field(default_factory=uuid4)
    version: int = 1
    title: str
    summary: str
    days: list[ItineraryDay]
    recommended_hotels: list[Hotel] = Field(default_factory=list)
    budget: BudgetBreakdown
    citations: list[Citation] = Field(default_factory=list)
    violations: list[ValidationViolation] = Field(default_factory=list)
    negotiation_options: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReplanRequest(BaseModel):
    reason: str
    locked_activity_ids: list[UUID] = Field(default_factory=list)
    updated_budget_inr: Decimal | None = Field(default=None, gt=0)
    preference_changes: dict[str, Any] = Field(default_factory=dict)
