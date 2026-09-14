from datetime import date, time
from decimal import Decimal

from app.models.schemas import Itinerary, ItineraryDay, Pace, Place, Preferences, TripRequest
from app.optimization.planner import build_day, calculate_budget, suitability_score, validate
from app.rag.hybrid import HybridRetriever
from app.rag.ingestion.pipeline import DocumentChunk, SourceDocument, chunk_document, extract
from app.repositories.state import InMemoryTripRepository
from app.services.trips import TravelPlannerService


def place(identifier: str, *, indoor: bool = False, cost: str = "100") -> Place:
    return Place(
        id=identifier,
        name=identifier.title(),
        destination="Chennai",
        categories=["museum" if indoor else "heritage"],
        latitude=13.0,
        longitude=80.2,
        visit_minutes=60,
        estimated_cost_inr=Decimal(cost),
        opening_time=time(9),
        closing_time=time(18),
        indoor=indoor,
    )


def test_chunking_keeps_provenance() -> None:
    source = SourceDocument(
        source_id="official-1",
        title="Guide",
        text=" ".join(f"word{i}" for i in range(800)),
        source_url="https://example.test",
        publisher="Tourism Department",
        location="Chennai",
        topic="heritage",
        license="test",
        retrieved_at="2026-01-01",
    )
    chunks = chunk_document(source, target_words=300, overlap_words=50)
    assert len(chunks) == 3
    assert all(chunk.publisher == "Tourism Department" for chunk in chunks)
    assert len({chunk.id for chunk in chunks}) == 3


async def test_hybrid_keyword_retrieval() -> None:
    chunks = [
        DocumentChunk("1", "a", "Museum", "An indoor museum in Chennai", "", "test", "Chennai", "museum", "test", "2026-01-01"),
        DocumentChunk("2", "b", "Beach", "An outdoor beach", "", "test", "Chennai", "beach", "test", "2026-01-01"),
    ]
    hits = await HybridRetriever(chunks).search("indoor museum Chennai")
    assert hits[0].chunk.id == "1"
    assert "bm25" in hits[0].channels


async def test_hybrid_fuses_external_channels() -> None:
    chunks = [
        DocumentChunk("1", "a", "Museum", "Chennai heritage", "", "test", "Chennai", "museum", "test", "2026-01-01"),
        DocumentChunk("2", "b", "Beach", "Mamallapuram coast", "", "test", "Mamallapuram", "beach", "test", "2026-01-01"),
    ]

    async def vector_search(query: str, limit: int) -> list[tuple[str, float]]:
        return [("2", 0.9)]

    async def keyword_search(query: str, limit: int) -> list[tuple[str, float]]:
        return [("2", 5.0)]

    async def graph_search(query: str, limit: int) -> list[str]:
        return ["2"]

    hits = await HybridRetriever(
        chunks,
        vector_search=vector_search,
        keyword_search=keyword_search,
        graph_search=graph_search,
    ).search("coast")
    assert hits[0].chunk.id == "2"
    assert set(hits[0].channels) == {"bm25", "graph", "opensearch", "vector"}


def test_json_extraction_is_searchable(tmp_path) -> None:
    path = tmp_path / "places.json"
    path.write_text('{"items": [{"name": "Shore Temple", "city": "Mamallapuram"}]}')
    text = extract(path)
    assert "Shore Temple" in text
    assert "Mamallapuram" in text


def test_schedule_and_budget_are_deterministic() -> None:
    places = [place("museum", indoor=True), place("temple")]
    matrix = [[0, 15], [15, 0]]
    day = build_day(
        date_value=date(2026, 1, 1), places=places, matrix=matrix,
        order=[0, 1], mode="drive",
    )
    assert len(day.activities) == 2
    assert day.activities[1].start_at >= day.activities[0].end_at
    budget = calculate_budget([day], limit=Decimal(10000), travellers=2)
    assert budget.total == (
        budget.attractions + budget.food + budget.transport
        + budget.accommodation + budget.contingency
    )
    assert not [item for item in validate([day], budget) if item.severity == "error"]


def test_accessibility_changes_suitability() -> None:
    accessible = place("accessible")
    accessible.accessibility = ["wheelchair"]
    inaccessible = place("inaccessible")
    preferences = Preferences(accessibility=["wheelchair"], interests=["heritage"])
    assert suitability_score(accessible, preferences) > suitability_score(inaccessible, preferences)


def test_repository_versions_and_deletes_memory() -> None:
    repository = InMemoryTripRepository()
    request = TripRequest(
        origin="Chennai", destinations=["Chennai"], start_date=date(2026, 1, 1),
        days=1, budget_inr=Decimal(5000), preferences=Preferences(pace=Pace.RELAXED),
    )
    first = Itinerary(
        title="Test", summary="Test", days=[ItineraryDay(date=request.start_date)],
        budget=calculate_budget([], limit=request.budget_inr, travellers=1),
    )
    second = first.model_copy(update={"version": 2})
    repository.save_request(first.trip_id, request)
    repository.save_version(first)
    repository.save_version(second)
    repository.save_preferences(request.user_id, request.preferences)
    assert repository.get_version(first.trip_id).version == 2
    assert len(repository.versions(first.trip_id)) == 2
    assert repository.delete_preferences(request.user_id)
    assert repository.get_preferences(request.user_id) is None


def test_llm_summary_must_match_structured_trip_facts() -> None:
    request = TripRequest(
        origin="Chennai",
        destinations=["Chennai"],
        start_date=date(2026, 1, 1),
        days=2,
        budget_inr=Decimal(15000),
    )
    assert TravelPlannerService._summary_is_consistent(
        "A 2-day Chennai itinerary with heritage highlights.", request
    )
    assert not TravelPlannerService._summary_is_consistent(
        "A 2-day Chennai itinerary completed in a single day with a restaurant stay.",
        request,
    )
