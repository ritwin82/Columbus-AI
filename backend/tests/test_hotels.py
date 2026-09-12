from collections import Counter
from decimal import Decimal

from app.repositories.hotels import HotelRepository


def test_static_hotel_catalogue_has_balanced_fifty_records() -> None:
    repository = HotelRepository()
    hotels = repository.all()
    assert len(hotels) == 50
    assert Counter(hotel.destination for hotel in hotels) == {
        "Chennai": 20,
        "Mamallapuram": 15,
        "Puducherry": 15,
    }
    assert len({hotel.id for hotel in hotels}) == 50


def test_hotel_search_and_budget_recommendation() -> None:
    repository = HotelRepository()
    results = repository.search(
        "Chennai",
        max_price_inr=Decimal(3000),
        limit=10,
    )
    assert results
    assert all(hotel.estimated_price_from_inr <= 3000 for hotel in results)
    recommendation = repository.recommend("Mamallapuram", Decimal(2600))
    assert recommendation is not None
    assert recommendation.estimated_price_from_inr <= 2600
