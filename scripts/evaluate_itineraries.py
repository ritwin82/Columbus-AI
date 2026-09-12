"""Run a reproducible 54-case itinerary feasibility evaluation."""

from __future__ import annotations

import asyncio
import sys
from datetime import date
from decimal import Decimal
from itertools import product
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import Settings
from app.core.container import build_container
from app.models.schemas import Preferences, TripRequest


async def main() -> None:
    container = build_container(
        Settings(
            enable_local_models=False,
            persistence_backend="memory",
            rag_mode="local",
            use_mock_providers=True,
        )
    )
    destinations = [["Chennai"], ["Mamallapuram"], ["Puducherry"]]
    budgets = [Decimal(8_000), Decimal(15_000), Decimal(25_000)]
    paces = ["relaxed", "moderate", "packed"]
    accessibility_options = [[], ["elderly_friendly"]]
    cases = list(product(destinations, budgets, paces, accessibility_options))
    feasible = budget_compliant = scheduled = 0
    try:
        for index, (places, budget, pace, accessibility) in enumerate(cases):
            request = TripRequest(
                user_id=f"evaluation-{index}",
                origin="Chennai",
                destinations=places,
                start_date=date(2026, 11, 10),
                days=1,
                travellers=2,
                budget_inr=budget,
                preferences=Preferences(
                    interests=["heritage", "museum"],
                    dietary=["vegetarian"],
                    accessibility=accessibility,
                    pace=pace,
                ),
            )
            itinerary = await container.workflow.run(request)
            errors = [item for item in itinerary.violations if item.severity == "error"]
            feasible += not errors
            budget_compliant += itinerary.budget.total <= itinerary.budget.limit
            scheduled += bool(itinerary.days[0].activities)
    finally:
        await container.close()

    total = len(cases)
    print(f"cases={total}")
    print(f"feasibility_rate={feasible / total:.2%}")
    print(f"budget_compliance_rate={budget_compliant / total:.2%}")
    print(f"non_empty_itinerary_rate={scheduled / total:.2%}")


if __name__ == "__main__":
    asyncio.run(main())
