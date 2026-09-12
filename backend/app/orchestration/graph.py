"""LangGraph workflow for generation, validation, and bounded reflection."""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.models.schemas import Itinerary, ReplanRequest, TripRequest
from app.services.trips import TravelPlannerService


class WorkflowState(TypedDict, total=False):
    request: TripRequest
    itinerary: Itinerary
    reflection_count: int


class TravelWorkflow:
    def __init__(self, service: TravelPlannerService, max_reflections: int = 3) -> None:
        self.service = service
        self.max_reflections = max_reflections
        builder = StateGraph(WorkflowState)
        builder.add_node("plan", self._plan)
        builder.add_node("reflect_and_repair", self._reflect_and_repair)
        builder.add_edge(START, "plan")
        builder.add_conditional_edges(
            "plan", self._next_step,
            {"repair": "reflect_and_repair", "done": END},
        )
        builder.add_conditional_edges(
            "reflect_and_repair", self._next_step,
            {"repair": "reflect_and_repair", "done": END},
        )
        self.graph = builder.compile()

    async def _plan(self, state: WorkflowState) -> WorkflowState:
        itinerary = await self.service.generate(state["request"])
        return {"itinerary": itinerary, "reflection_count": 0}

    async def _reflect_and_repair(self, state: WorkflowState) -> WorkflowState:
        itinerary = state["itinerary"]
        count = state.get("reflection_count", 0) + 1
        errors = [item for item in itinerary.violations if item.severity == "error"]
        reason = "; ".join(item.message for item in errors)
        changes = {}
        if any(item.code in {"budget", "overlap"} for item in errors):
            changes["pace"] = "relaxed"
        repaired = await self.service.replan(
            itinerary.trip_id,
            ReplanRequest(reason=f"Automatic validation repair: {reason}", preference_changes=changes),
        )
        return {"itinerary": repaired, "reflection_count": count}

    def _next_step(self, state: WorkflowState) -> str:
        errors = [item for item in state["itinerary"].violations if item.severity == "error"]
        if errors and state.get("reflection_count", 0) < self.max_reflections:
            return "repair"
        return "done"

    async def run(self, request: TripRequest) -> Itinerary:
        result = await self.graph.ainvoke({"request": request, "reflection_count": 0})
        return result["itinerary"]
