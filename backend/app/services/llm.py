"""Local Ollama gateway with schema-aware generation."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)


class ModelUnavailable(RuntimeError):
    """Raised when the configured local model server cannot answer."""


class OllamaGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=settings.request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            response = await self._client.get("/api/tags")
            return response.is_success
        except httpx.HTTPError:
            return False

    async def installed_models(self) -> list[str]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            return sorted(
                item["name"] for item in response.json().get("models", []) if item.get("name")
            )
        except (httpx.HTTPError, KeyError, TypeError):
            return []

    async def readiness(self) -> dict[str, Any]:
        installed = await self.installed_models()
        required = [
            self.settings.planner_model,
            self.settings.task_model,
            self.settings.embedding_model,
        ]

        def available(model: str) -> bool:
            base = model.split(":", 1)[0]
            if ":" in model:
                return model in installed
            return any(name == model or name.split(":", 1)[0] == base for name in installed)

        return {
            "reachable": bool(installed),
            "installed": installed,
            "required": required,
            "missing": [model for model in required if not available(model)],
            "chat_fallback": {
                "model": self.settings.fallback_chat_model,
                "available": available(self.settings.fallback_chat_model),
            },
            "embedding_fallback": {
                "model": self.settings.fallback_embedding_model,
                "available": available(self.settings.fallback_embedding_model),
            },
        }

    async def chat(
        self,
        *,
        prompt: str,
        system: str,
        model: str | None = None,
        schema: type[T] | None = None,
        temperature: float = 0.1,
    ) -> str | T:
        payload: dict[str, Any] = {
            "model": model or self.settings.task_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": temperature},
        }
        if schema:
            payload["format"] = schema.model_json_schema()

        try:
            response = await self._client.post("/api/chat", json=payload)
            if (
                response.status_code == 404
                and self.settings.fallback_chat_model
                and payload["model"] != self.settings.fallback_chat_model
            ):
                payload["model"] = self.settings.fallback_chat_model
                response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"Ollama request failed: {exc}") from exc

        content = response.json()["message"]["content"]
        if not schema:
            return content
        return schema.model_validate(json.loads(content))

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.settings.embedding_model, "input": texts}
        try:
            response = await self._client.post("/api/embed", json=payload)
            if (
                response.status_code == 404
                and self.settings.fallback_embedding_model
                and payload["model"] != self.settings.fallback_embedding_model
            ):
                payload["model"] = self.settings.fallback_embedding_model
                response = await self._client.post("/api/embed", json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"Ollama embedding request failed: {exc}") from exc
        return response.json()["embeddings"]
