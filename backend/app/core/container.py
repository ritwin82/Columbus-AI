"""Application dependency container."""

from dataclasses import dataclass

from app.agents.tasks import TaskAgents
from app.core.config import Settings, get_settings
from app.integrations.providers import (
    DemoProvider,
    GooglePlacesProvider,
    GoogleRoutesProvider,
    OpenWeatherProvider,
    ResilientProvider,
)
from app.orchestration.graph import TravelWorkflow
from app.repositories.catalog import CatalogueRepository
from app.repositories.hotels import HotelRepository
from app.repositories.state import InMemoryTripRepository, SqlTripRepository, TripRepository
from app.services.knowledge import KnowledgeService
from app.services.llm import OllamaGateway
from app.services.reranker import LocalReranker
from app.services.trips import TravelPlannerService


@dataclass
class Container:
    settings: Settings
    repository: TripRepository
    catalogue: CatalogueRepository
    hotels: HotelRepository
    llm: OllamaGateway
    trips: TravelPlannerService
    workflow: TravelWorkflow
    task_agents: TaskAgents
    knowledge: KnowledgeService

    async def close(self) -> None:
        await self.knowledge.close()
        await self.llm.close()


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    catalogue = CatalogueRepository()
    hotels = HotelRepository()
    repository: TripRepository = (
        SqlTripRepository(settings.postgres_url)
        if settings.persistence_backend == "postgres"
        else InMemoryTripRepository()
    )
    llm = OllamaGateway(settings)
    demo = DemoProvider(catalogue.all())
    reranker = LocalReranker(settings.reranker_model) if settings.enable_local_reranker else None
    knowledge = KnowledgeService(catalogue, settings, llm, reranker)

    live_places = None
    live_routes = None
    live_weather = None
    if not settings.use_mock_providers:
        if settings.google_maps_api_key:
            live_places = GooglePlacesProvider(
                settings.google_maps_api_key, settings.request_timeout_seconds
            )
            live_routes = GoogleRoutesProvider(
                settings.google_maps_api_key, settings.request_timeout_seconds
            )
        if settings.openweather_api_key:
            live_weather = OpenWeatherProvider(
                settings.openweather_api_key, settings.request_timeout_seconds
            )
    resilient = ResilientProvider(
        demo, places=live_places, routes=live_routes, weather=live_weather
    )

    trips = TravelPlannerService(
        settings=settings,
        catalogue=catalogue,
        repository=repository,
        places=resilient,
        routes=resilient,
        weather=resilient,
        llm=llm,
        knowledge=knowledge,
        hotels=hotels,
    )
    workflow = TravelWorkflow(trips, settings.max_reflections)
    task_agents = TaskAgents(llm, settings)
    return Container(
        settings, repository, catalogue, hotels, llm, trips, workflow, task_agents, knowledge
    )
