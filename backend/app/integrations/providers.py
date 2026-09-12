"""Live travel provider contracts and reference implementations."""

from __future__ import annotations

from datetime import UTC, datetime
from math import atan2, cos, radians, sin, sqrt
from typing import Protocol

import httpx

from app.models.schemas import Citation, Place, RouteLeg, TravelMode, WeatherWindow


class PlaceProvider(Protocol):
    async def search(self, query: str, destination: str) -> list[Place]: ...


class RouteProvider(Protocol):
    async def matrix(self, places: list[Place], mode: TravelMode) -> list[list[int]]: ...


class WeatherProvider(Protocol):
    async def forecast(self, latitude: float, longitude: float) -> list[WeatherWindow]: ...


class GooglePlacesProvider:
    def __init__(self, api_key: str, timeout: float = 20) -> None:
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=timeout)

    async def search(self, query: str, destination: str) -> list[Place]:
        response = await self.client.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,"
                    "places.location,places.types,places.currentOpeningHours,"
                    "places.businessStatus"
                ),
            },
            json={"textQuery": f"{query} in {destination}", "languageCode": "en"},
        )
        response.raise_for_status()
        now = datetime.now(UTC)
        return [
            Place(
                id=item["id"],
                name=item["displayName"]["text"],
                destination=destination,
                categories=item.get("types", ["point_of_interest"]),
                description=item.get("formattedAddress", ""),
                latitude=item["location"]["latitude"],
                longitude=item["location"]["longitude"],
                live_status=item.get("businessStatus", "unknown").lower(),
                citations=[
                    Citation(
                        title="Google Places live result",
                        publisher="Google Maps Platform",
                        retrieved_at=now,
                        reliability=0.9,
                        is_live=True,
                    )
                ],
            )
            for item in response.json().get("places", [])
        ]


class GoogleRoutesProvider:
    def __init__(self, api_key: str, timeout: float = 20) -> None:
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=timeout)

    async def matrix(self, places: list[Place], mode: TravelMode) -> list[list[int]]:
        if not places:
            return []
        travel_mode = {
            TravelMode.WALK: "WALK",
            TravelMode.TRANSIT: "TRANSIT",
            TravelMode.DRIVE: "DRIVE",
            TravelMode.TWO_WHEELER: "TWO_WHEELER",
        }[mode]
        waypoints = [
            {"waypoint": {"location": {"latLng": {
                "latitude": place.latitude, "longitude": place.longitude
            }}}}
            for place in places
        ]
        response = await self.client.post(
            "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            headers={
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "originIndex,destinationIndex,duration,status,condition",
            },
            json={"origins": waypoints, "destinations": waypoints, "travelMode": travel_mode},
        )
        response.raise_for_status()
        matrix = [[0 for _ in places] for _ in places]
        for item in response.json():
            seconds = int(item.get("duration", "0s").removesuffix("s"))
            matrix[item["originIndex"]][item["destinationIndex"]] = max(1, seconds // 60)
        return matrix


class OpenWeatherProvider:
    def __init__(self, api_key: str, timeout: float = 20) -> None:
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=timeout)

    async def forecast(self, latitude: float, longitude: float) -> list[WeatherWindow]:
        response = await self.client.get(
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"lat": latitude, "lon": longitude, "appid": self.api_key, "units": "metric"},
        )
        response.raise_for_status()
        return [
            WeatherWindow(
                at=datetime.fromtimestamp(item["dt"], UTC),
                condition=item["weather"][0]["main"].lower(),
                temperature_c=item["main"]["temp"],
                rain_probability=item.get("pop", 0),
                wind_kph=item.get("wind", {}).get("speed", 0) * 3.6,
                source="OpenWeather",
            )
            for item in response.json().get("list", [])
        ]


class DemoProvider:
    """Deterministic provider for local development and automated tests."""

    def __init__(self, places: list[Place]) -> None:
        self.places = places

    async def search(self, query: str, destination: str) -> list[Place]:
        terms = set(query.lower().split())
        return [
            place for place in self.places
            if place.destination.lower() == destination.lower()
            and (not terms or terms.intersection(" ".join(place.categories).lower().split()))
        ] or [p for p in self.places if p.destination.lower() == destination.lower()]

    async def matrix(self, places: list[Place], mode: TravelMode) -> list[list[int]]:
        speeds = {TravelMode.WALK: 4.5, TravelMode.TRANSIT: 22, TravelMode.DRIVE: 30,
                  TravelMode.TWO_WHEELER: 28}
        return [[
            0 if left.id == right.id else max(5, round(self._distance(left, right) / speeds[mode] * 60))
            for right in places
        ] for left in places]

    async def forecast(self, latitude: float, longitude: float) -> list[WeatherWindow]:
        return []

    @staticmethod
    def _distance(left: Place, right: Place) -> float:
        earth_radius = 6371.0
        lat1, lat2 = radians(left.latitude), radians(right.latitude)
        d_lat = radians(right.latitude - left.latitude)
        d_lon = radians(right.longitude - left.longitude)
        value = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
        return earth_radius * 2 * atan2(sqrt(value), sqrt(1 - value))


class ResilientProvider:
    """Use live providers when healthy and deterministic data when they fail."""

    def __init__(
        self,
        fallback: DemoProvider,
        *,
        places: PlaceProvider | None = None,
        routes: RouteProvider | None = None,
        weather: WeatherProvider | None = None,
    ) -> None:
        self.fallback = fallback
        self.places = places
        self.routes = routes
        self.weather = weather

    async def search(self, query: str, destination: str) -> list[Place]:
        if self.places:
            try:
                results = await self.places.search(query, destination)
                if results:
                    return results
            except (httpx.HTTPError, KeyError, ValueError):
                pass
        return await self.fallback.search(query, destination)

    async def matrix(self, places: list[Place], mode: TravelMode) -> list[list[int]]:
        if self.routes:
            try:
                return await self.routes.matrix(places, mode)
            except (httpx.HTTPError, KeyError, ValueError):
                pass
        return await self.fallback.matrix(places, mode)

    async def forecast(self, latitude: float, longitude: float) -> list[WeatherWindow]:
        if self.weather:
            try:
                return await self.weather.forecast(latitude, longitude)
            except (httpx.HTTPError, KeyError, ValueError):
                pass
        return await self.fallback.forecast(latitude, longitude)


def route_leg(left: Place, right: Place, minutes: int, mode: TravelMode) -> RouteLeg:
    return RouteLeg(
        origin_id=left.id,
        destination_id=right.id,
        duration_minutes=minutes,
        distance_km=DemoProvider._distance(left, right),
        mode=mode,
    )
