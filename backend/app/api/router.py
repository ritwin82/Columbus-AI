"""Travel and memory HTTP endpoints."""

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.agents.tasks import IntentResult, NaturalLanguageQuery
from app.core.container import Container
from app.models.schemas import Hotel, Itinerary, Preferences, ReplanRequest, TripRequest
from app.services.knowledge import KnowledgeHit
from app.services.trips import TripNotFound

api_router = APIRouter()


def container(request: Request) -> Container:
    return request.app.state.container


@api_router.get("/status", tags=["system"])
async def service_status(request: Request) -> dict:
    dependencies = {
        "ollama": await container(request).llm.readiness(),
        "knowledge": container(request).knowledge.status(),
    }
    return {
        "service": "travelmind",
        "status": "ready",
        "mode": "mock" if container(request).settings.use_mock_providers else "live",
        "dependencies": dependencies,
    }


@api_router.post("/trips/generate", response_model=Itinerary, status_code=status.HTTP_201_CREATED)
async def generate_trip(payload: TripRequest, request: Request) -> Itinerary:
    return await container(request).workflow.run(payload)


@api_router.post("/intent", response_model=IntentResult)
async def extract_intent(payload: NaturalLanguageQuery, request: Request) -> IntentResult:
    return await container(request).task_agents.extract_intent(payload.text)


@api_router.get("/knowledge/search", response_model=list[KnowledgeHit])
async def search_knowledge(
    request: Request,
    query: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=8, ge=1, le=50),
) -> list[KnowledgeHit]:
    return await container(request).knowledge.search(query, limit)


@api_router.get("/hotels/search", response_model=list[Hotel])
async def search_hotels(
    request: Request,
    destination: str = Query(min_length=2, max_length=100),
    max_price_inr: Annotated[Decimal | None, Query(gt=0)] = None,
    price_tier: str | None = Query(default=None, max_length=50),
    accessibility: Annotated[list[str] | None, Query()] = None,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[Hotel]:
    return container(request).hotels.search(
        destination,
        max_price_inr=max_price_inr,
        price_tier=price_tier,
        accessibility=accessibility,
        limit=limit,
    )


@api_router.get("/trips/{trip_id}", response_model=Itinerary)
async def get_trip(trip_id: UUID, request: Request, version: int | None = Query(default=None, ge=1)) -> Itinerary:
    result = container(request).repository.get_version(trip_id, version)
    if not result:
        raise HTTPException(status_code=404, detail="Trip or version not found")
    return result


@api_router.get("/trips/{trip_id}/versions", response_model=list[Itinerary])
async def trip_versions(trip_id: UUID, request: Request) -> list[Itinerary]:
    return container(request).repository.versions(trip_id)


@api_router.post("/trips/{trip_id}/replan", response_model=Itinerary)
async def replan_trip(trip_id: UUID, payload: ReplanRequest, request: Request) -> Itinerary:
    try:
        return await container(request).trips.replan(trip_id, payload)
    except TripNotFound as exc:
        raise HTTPException(status_code=404, detail="Trip not found") from exc


@api_router.get("/users/{user_id}/preferences", response_model=Preferences)
async def get_preferences(user_id: str, request: Request) -> Preferences:
    result = container(request).repository.get_preferences(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return result


@api_router.delete("/users/{user_id}/preferences", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preferences(user_id: str, request: Request) -> None:
    container(request).repository.delete_preferences(user_id)
