from fastapi.testclient import TestClient

from app.main import app


def test_health_and_generate_replan_flow() -> None:
    payload = {
        "user_id": "student-demo",
        "origin": "Chennai",
        "destinations": ["Chennai", "Mamallapuram", "Puducherry"],
        "start_date": "2026-11-10",
        "days": 3,
        "travellers": 2,
        "budget_inr": "25000",
        "preferences": {
            "interests": ["history", "museum", "heritage"],
            "dietary": ["vegetarian"],
            "accessibility": [],
            "pace": "moderate",
            "travel_mode": "drive",
            "crowd_tolerance": 5,
        },
    }
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        created = client.post("/api/v1/trips/generate", json=payload)
        assert created.status_code == 201, created.text
        itinerary = created.json()
        assert itinerary["version"] >= 1
        assert len(itinerary["days"]) == 3
        assert len(itinerary["recommended_hotels"]) == 2

        trip_id = itinerary["trip_id"]
        fetched = client.get(f"/api/v1/trips/{trip_id}")
        assert fetched.status_code == 200

        activity_ids = [
            activity["id"] for day in itinerary["days"] for activity in day["activities"]
        ]
        replanned = client.post(
            f"/api/v1/trips/{trip_id}/replan",
            json={
                "reason": "Prefer a slower schedule",
                "locked_activity_ids": activity_ids[:1],
                "preference_changes": {"pace": "relaxed"},
            },
        )
        assert replanned.status_code == 200, replanned.text
        assert replanned.json()["version"] == itinerary["version"] + 1

        versions = client.get(f"/api/v1/trips/{trip_id}/versions")
        assert len(versions.json()) >= 2


def test_intent_and_knowledge_endpoints() -> None:
    with TestClient(app) as client:
        intent = client.post(
            "/api/v1/intent",
            json={"text": "Quiet 3 days in Chennai under Rs 20,000 with vegetarian food"},
        )
        assert intent.status_code == 200
        assert intent.json()["days"] == 3
        assert intent.json()["budget_inr"] == "20000"

        knowledge = client.get(
            "/api/v1/knowledge/search",
            params={"query": "indoor museum Chennai"},
        )
        assert knowledge.status_code == 200
        results = knowledge.json()
        assert results
        assert any("museum" in item["content"].casefold() for item in results)

        hotels = client.get(
            "/api/v1/hotels/search",
            params={"destination": "Puducherry", "max_price_inr": "4000"},
        )
        assert hotels.status_code == 200
        assert hotels.json()
        assert all(
            float(hotel["estimated_price_from_inr"]) <= 4000
            for hotel in hotels.json()
        )


def test_frontend_origin_is_allowed() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/knowledge/search",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == (
            "http://localhost:5173"
        )
