"""Deterministic candidate ranking, routing, scheduling, and validation."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from itertools import pairwise
from math import asin, cos, radians, sin, sqrt

from app.integrations.providers import route_leg
from app.models.schemas import (
    Activity,
    BudgetBreakdown,
    ItineraryDay,
    Place,
    Preferences,
    TravelMode,
    ValidationViolation,
    WeatherWindow,
)


def suitability_score(place: Place, preferences: Preferences, weather_risk: bool = False) -> float:
    categories = {item.casefold() for item in place.categories}
    interests = {item.casefold() for item in preferences.interests}
    accessibility = {item.casefold() for item in place.accessibility}
    required_accessibility = {item.casefold() for item in preferences.accessibility}
    score = 2.0 * len(categories & interests)
    score += max(0, preferences.crowd_tolerance - place.crowd_level) * 0.15
    score += 1.5 if required_accessibility.issubset(accessibility) else -4.0
    score -= 3.0 if categories.intersection(map(str.casefold, preferences.excluded_categories)) else 0
    score -= 3.0 if weather_risk and not place.indoor else 0
    score += sum(citation.reliability for citation in place.citations) / max(1, len(place.citations))
    return score


def optimize_order(matrix: list[list[int]], scores: list[float], max_places: int) -> list[int]:
    """Prize-weighted route order using OR-Tools, with a deterministic fallback."""
    if not matrix:
        return []
    try:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    except ImportError:
        return sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)[:max_places]

    size = len(matrix)
    manager = pywrapcp.RoutingIndexManager(size, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def transit(from_index: int, to_index: int) -> int:
        return matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    callback = routing.RegisterTransitCallback(transit)
    routing.SetArcCostEvaluatorOfAllVehicles(callback)
    for node in range(1, size):
        penalty = max(1, int(10_000 + scores[node] * 1_000))
        routing.AddDisjunction([manager.NodeToIndex(node)], penalty)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.time_limit.seconds = 2
    solution = routing.SolveWithParameters(params)
    if not solution:
        return sorted(range(size), key=lambda index: scores[index], reverse=True)[:max_places]
    order: list[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    return order[:max_places]


def build_day(
    *,
    date_value,
    places: list[Place],
    matrix: list[list[int]],
    order: list[int],
    mode: TravelMode,
    start_hour: int = 9,
    end_hour: int = 19,
) -> ItineraryDay:
    cursor = datetime.combine(date_value, time(start_hour, 0))
    day_end = datetime.combine(date_value, time(end_hour, 0))
    activities: list[Activity] = []
    previous_index: int | None = None
    for index in order:
        place = places[index]
        travel_minutes = matrix[previous_index][index] if previous_index is not None else 0
        cursor += timedelta(minutes=travel_minutes)
        opens = datetime.combine(date_value, place.opening_time)
        closes = datetime.combine(date_value, place.closing_time)
        cursor = max(cursor, opens)
        end_at = cursor + timedelta(minutes=place.visit_minutes)
        if end_at > min(closes, day_end):
            continue
        leg = None
        if previous_index is not None:
            leg = route_leg(places[previous_index], place, travel_minutes, mode)
        activities.append(Activity(
            place=place,
            start_at=cursor,
            end_at=end_at,
            route_from_previous=leg,
            estimated_cost_inr=place.estimated_cost_inr,
            reason="Selected from verified candidates based on preferences and route efficiency.",
        ))
        cursor = end_at
        previous_index = index
    return ItineraryDay(date=date_value, activities=activities)


def calculate_budget(
    days: list[ItineraryDay],
    *,
    limit: Decimal,
    travellers: int,
    daily_food_per_person: Decimal = Decimal(900),
    daily_food_costs_per_person: list[Decimal] | None = None,
    accommodation_per_night: Decimal = Decimal(2500),
    travel_mode: TravelMode = TravelMode.DRIVE,
) -> BudgetBreakdown:
    attractions = sum(
        (activity.estimated_cost_inr for day in days for activity in day.activities),
        Decimal(0),
    ) * travellers
    daily_food = daily_food_costs_per_person or [daily_food_per_person for _ in days]
    food = sum(daily_food, Decimal(0)) * travellers
    accommodation = accommodation_per_night * max(0, len(days) - 1)
    routed_km = sum(
        (
            Decimal(str(activity.route_from_previous.distance_km))
            for day in days
            for activity in day.activities
            if activity.route_from_previous
        ),
        Decimal(0),
    )
    transfer_km = Decimal(0)
    populated_days = [day for day in days if day.activities]
    for previous, current in pairwise(populated_days):
        left = previous.activities[-1].place
        right = current.activities[0].place
        transfer_km += Decimal(str(_road_distance_km(left, right)))
    cost_per_km = {
        TravelMode.WALK: Decimal(0),
        TravelMode.TRANSIT: Decimal(3),
        TravelMode.DRIVE: Decimal(18),
        TravelMode.TWO_WHEELER: Decimal(7),
    }[TravelMode(travel_mode)]
    passenger_factor = travellers if TravelMode(travel_mode) == TravelMode.TRANSIT else 1
    local_access = {
        TravelMode.WALK: Decimal(0),
        TravelMode.TRANSIT: Decimal(80),
        TravelMode.DRIVE: Decimal(180),
        TravelMode.TWO_WHEELER: Decimal(90),
    }[TravelMode(travel_mode)] * len(populated_days) * passenger_factor
    transport = (
        (routed_km + transfer_km) * cost_per_km * passenger_factor + local_access
    ).quantize(Decimal(1))
    subtotal = attractions + food + accommodation + transport
    contingency = (subtotal * Decimal("0.10")).quantize(Decimal(1))
    return BudgetBreakdown(
        attractions=attractions,
        food=food,
        transport=transport,
        accommodation=accommodation,
        contingency=contingency,
        total=subtotal + contingency,
        limit=limit,
    )


def _road_distance_km(left: Place, right: Place) -> float:
    """Approximate road distance from coordinates using a conservative road factor."""
    earth_radius_km = 6371.0
    lat1, lon1 = radians(left.latitude), radians(left.longitude)
    lat2, lon2 = radians(right.latitude), radians(right.longitude)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    straight_line = 2 * earth_radius_km * asin(sqrt(value))
    return straight_line * 1.2


def weather_risk(place: Place, forecasts: list[WeatherWindow], start_at: datetime) -> str | None:
    if place.indoor:
        return None
    relevant = min(forecasts, key=lambda item: abs((item.at.replace(tzinfo=None) - start_at).total_seconds()), default=None)
    if not relevant:
        return None
    if relevant.rain_probability >= 0.6:
        return f"Outdoor activity has {relevant.rain_probability:.0%} rain probability"
    if relevant.temperature_c >= 37 and 10 <= start_at.hour <= 16:
        return f"Outdoor activity scheduled during {relevant.temperature_c:.0f}°C heat"
    return None


def validate(
    days: list[ItineraryDay],
    budget: BudgetBreakdown,
    forecasts: list[WeatherWindow] | None = None,
) -> list[ValidationViolation]:
    violations: list[ValidationViolation] = []
    for day in days:
        previous: Activity | None = None
        for activity in day.activities:
            if previous and activity.start_at < previous.end_at:
                violations.append(ValidationViolation(
                    code="overlap", message="Activities overlap", day=day.date,
                    activity_id=activity.id,
                ))
            if activity.start_at.time() < activity.place.opening_time or activity.end_at.time() > activity.place.closing_time:
                violations.append(ValidationViolation(
                    code="closed", message=f"{activity.place.name} is outside its opening window",
                    day=day.date, activity_id=activity.id,
                ))
            risk = weather_risk(activity.place, forecasts or [], activity.start_at)
            if risk:
                violations.append(ValidationViolation(
                    code="weather", message=risk, day=day.date,
                    activity_id=activity.id, severity="warning",
                ))
            previous = activity
    if budget.total > budget.limit:
        violations.append(ValidationViolation(
            code="budget", message=f"Estimated total ₹{budget.total} exceeds ₹{budget.limit}"
        ))
    return violations
