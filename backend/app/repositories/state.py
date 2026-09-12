"""Trip version and preference persistence."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Protocol
from uuid import UUID

from app.models.schemas import Itinerary, Preferences, TripRequest


class TripRepository(Protocol):
    def save_request(self, trip_id: UUID, request: TripRequest) -> None: ...
    def get_request(self, trip_id: UUID) -> TripRequest | None: ...
    def save_version(self, itinerary: Itinerary) -> None: ...
    def get_version(self, trip_id: UUID, version: int | None = None) -> Itinerary | None: ...
    def versions(self, trip_id: UUID) -> list[Itinerary]: ...
    def save_preferences(self, user_id: str, preferences: Preferences) -> None: ...
    def get_preferences(self, user_id: str) -> Preferences | None: ...
    def delete_preferences(self, user_id: str) -> bool: ...


class InMemoryTripRepository:
    """Thread-safe repository used for tests and zero-configuration local runs."""

    def __init__(self) -> None:
        self._requests: dict[UUID, TripRequest] = {}
        self._versions: defaultdict[UUID, list[Itinerary]] = defaultdict(list)
        self._preferences: dict[str, Preferences] = {}
        self._lock = RLock()

    def save_request(self, trip_id: UUID, request: TripRequest) -> None:
        with self._lock:
            self._requests[trip_id] = request.model_copy(deep=True)

    def get_request(self, trip_id: UUID) -> TripRequest | None:
        with self._lock:
            value = self._requests.get(trip_id)
            return value.model_copy(deep=True) if value else None

    def save_version(self, itinerary: Itinerary) -> None:
        with self._lock:
            versions = self._versions[itinerary.trip_id]
            versions[:] = [item for item in versions if item.version != itinerary.version]
            versions.append(itinerary.model_copy(deep=True))
            versions.sort(key=lambda item: item.version)

    def get_version(self, trip_id: UUID, version: int | None = None) -> Itinerary | None:
        with self._lock:
            values = self._versions.get(trip_id, [])
            if not values:
                return None
            result = values[-1] if version is None else next((v for v in values if v.version == version), None)
            return result.model_copy(deep=True) if result else None

    def versions(self, trip_id: UUID) -> list[Itinerary]:
        with self._lock:
            return [value.model_copy(deep=True) for value in self._versions.get(trip_id, [])]

    def save_preferences(self, user_id: str, preferences: Preferences) -> None:
        with self._lock:
            self._preferences[user_id] = preferences.model_copy(deep=True)

    def get_preferences(self, user_id: str) -> Preferences | None:
        with self._lock:
            result = self._preferences.get(user_id)
            return result.model_copy(deep=True) if result else None

    def delete_preferences(self, user_id: str) -> bool:
        with self._lock:
            return self._preferences.pop(user_id, None) is not None


class SqlTripRepository:
    """Compact PostgreSQL/SQLite implementation using JSON payloads."""

    def __init__(self, database_url: str) -> None:
        from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, delete, select

        self._select = select
        self._delete = delete
        self.engine = create_engine(database_url)
        metadata = MetaData()
        self.requests = Table(
            "trip_requests", metadata,
            Column("trip_id", String(36), primary_key=True),
            Column("payload", Text, nullable=False),
        )
        self.itineraries = Table(
            "itinerary_versions", metadata,
            Column("key", String(64), primary_key=True),
            Column("trip_id", String(36), index=True, nullable=False),
            Column("version", String(10), nullable=False),
            Column("payload", Text, nullable=False),
        )
        self.preferences = Table(
            "user_preferences", metadata,
            Column("user_id", String(255), primary_key=True),
            Column("payload", Text, nullable=False),
        )
        metadata.create_all(self.engine)

    @staticmethod
    def _dump(model) -> str:
        return model.model_dump_json()

    def _upsert(self, table, key: dict, values: dict) -> None:
        with self.engine.begin() as connection:
            connection.execute(self._delete(table).where(*[table.c[k] == v for k, v in key.items()]))
            connection.execute(table.insert().values(**key, **values))

    def save_request(self, trip_id: UUID, request: TripRequest) -> None:
        self._upsert(self.requests, {"trip_id": str(trip_id)}, {"payload": self._dump(request)})

    def get_request(self, trip_id: UUID) -> TripRequest | None:
        with self.engine.connect() as connection:
            row = connection.execute(self._select(self.requests.c.payload).where(self.requests.c.trip_id == str(trip_id))).scalar_one_or_none()
        return TripRequest.model_validate_json(row) if row else None

    def save_version(self, itinerary: Itinerary) -> None:
        trip_id = str(itinerary.trip_id)
        self._upsert(
            self.itineraries,
            {"key": f"{trip_id}:{itinerary.version}"},
            {"trip_id": trip_id, "version": str(itinerary.version), "payload": self._dump(itinerary)},
        )

    def versions(self, trip_id: UUID) -> list[Itinerary]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                self._select(self.itineraries.c.payload).where(self.itineraries.c.trip_id == str(trip_id))
            ).scalars()
            values = [Itinerary.model_validate_json(row) for row in rows]
        return sorted(values, key=lambda item: item.version)

    def get_version(self, trip_id: UUID, version: int | None = None) -> Itinerary | None:
        values = self.versions(trip_id)
        if not values:
            return None
        return values[-1] if version is None else next((v for v in values if v.version == version), None)

    def save_preferences(self, user_id: str, preferences: Preferences) -> None:
        self._upsert(self.preferences, {"user_id": user_id}, {"payload": self._dump(preferences)})

    def get_preferences(self, user_id: str) -> Preferences | None:
        with self.engine.connect() as connection:
            row = connection.execute(self._select(self.preferences.c.payload).where(self.preferences.c.user_id == user_id)).scalar_one_or_none()
        return Preferences.model_validate_json(row) if row else None

    def delete_preferences(self, user_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(self._delete(self.preferences).where(self.preferences.c.user_id == user_id))
        return bool(result.rowcount)
