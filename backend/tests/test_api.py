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
        assert all(day["restaurant"] for day in itinerary["days"])
        assert all(day["restaurant"]["rating"] for day in itinerary["days"])
        place_names = [
            activity["place"]["name"].casefold()
            for day in itinerary["days"]
            for activity in day["activities"]
        ]
        assert len(place_names) == len(set(place_names))
        assert all(
            activity["place"]["rating"] is not None
            for day in itinerary["days"]
            for activity in day["activities"]
        )
        assert float(itinerary["budget"]["food"]) > 0
        assert float(itinerary["budget"]["transport"]) > 0

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
        assert intent.json()["pace"] == "relaxed"

        aliases = client.post(
            "/api/v1/intent",
            json={
                "text": "Couple trip from Bengaluru to Madras and Pondicherry for three days, 25k, by bus"
            },
        )
        assert aliases.status_code == 200
        parsed = aliases.json()
        assert parsed["destinations"] == ["Chennai", "Puducherry"]
        assert parsed["days"] == 3
        assert parsed["travellers"] == 2
        assert parsed["budget_inr"] == "25000"
        assert parsed["travel_mode"] == "transit"

        incomplete = client.post(
            "/api/v1/intent", json={"text": "I want a quiet heritage trip"}
        )
        assert incomplete.status_code == 200
        missing = incomplete.json()
        assert set(missing["missing_required_fields"]) == {
            "destinations", "days", "budget_inr"
        }
        assert "please tell me" in missing["clarification_question"].casefold()

        unsupported_intent = client.post(
            "/api/v1/intent",
            json={"text": "Plan a 2 day Goa trip with Rs 20,000 budget"},
        )
        assert unsupported_intent.status_code == 200
        assert unsupported_intent.json()["destinations"] == ["Goa"]
        assert "destinations" not in unsupported_intent.json()["missing_required_fields"]

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


def test_infeasible_trip_returns_human_explanation() -> None:
    payload = {
        "origin": "Chennai",
        "destinations": ["Goa"],
        "start_date": "2026-11-10",
        "days": 2,
        "budget_inr": "20000",
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/trips/generate", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail["message"], str)
        assert detail["reasons"]
        assert detail["suggestions"]
        assert "Goa" in " ".join(detail["reasons"])


def test_repeated_destination_uses_unique_places_and_restaurants() -> None:
    payload = {
        "origin": "Chennai",
        "destinations": ["Chennai"],
        "start_date": "2026-11-10",
        "days": 3,
        "travellers": 2,
        "budget_inr": "50000",
        "preferences": {"pace": "moderate", "travel_mode": "drive"},
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/trips/generate", json=payload)
        assert response.status_code == 201, response.text
        days = response.json()["days"]
        places = [
            activity["place"]["name"].casefold()
            for day in days
            for activity in day["activities"]
        ]
        restaurants = [day["restaurant"]["id"] for day in days]
        assert all(day["activities"] for day in days)
        assert len(places) == len(set(places))
        assert len(restaurants) == len(set(restaurants))


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


def test_frontend_and_preference_memory_endpoints() -> None:
    preferences = {
        "interests": ["heritage", "food"],
        "dietary": ["vegetarian"],
        "accessibility": [],
        "excluded_categories": [],
        "pace": "relaxed",
        "travel_mode": "drive",
        "crowd_tolerance": 3,
        "preferred_language": "en",
    }
    with TestClient(app) as client:
        frontend = client.get("/")
        assert frontend.status_code == 200
        assert "Columbus AI" in frontend.text
        frontend_script = client.get("/app.js")
        assert frontend_script.status_code == 200
        for endpoint in (
            "/status",
            "/intent",
            "/knowledge/search",
            "/hotels/search",
            "/weather",
            "/trips/generate",
            "/versions",
            "/replan",
            "/preferences",
        ):
            assert endpoint in frontend_script.text

        saved = client.put("/api/v1/users/browser-user/preferences", json=preferences)
        assert saved.status_code == 200
        assert saved.json()["pace"] == "relaxed"

        recalled = client.get("/api/v1/users/browser-user/preferences")
        assert recalled.status_code == 200
        assert recalled.json()["dietary"] == ["vegetarian"]

        deleted = client.delete("/api/v1/users/browser-user/preferences")
        assert deleted.status_code == 204
        assert client.get("/api/v1/users/browser-user/preferences").status_code == 404
