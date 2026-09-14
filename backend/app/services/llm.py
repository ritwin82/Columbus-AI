"""Resilient Ollama, Google AI, and OpenRouter model gateway."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import Settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class ModelUnavailable(RuntimeError):
    """Raised when none of the configured model providers can answer."""


class OllamaGateway:
    """Keep the original interface while adding cloud-provider failover."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        timeout = settings.request_timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url, timeout=timeout
        )
        self._google_client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            timeout=timeout,
        )
        self._openrouter_client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url, timeout=timeout
        )
        self.last_chat_provider: str | None = None
        self.last_embedding_provider: str | None = None

    async def close(self) -> None:
        await self._client.aclose()
        await self._google_client.aclose()
        await self._openrouter_client.aclose()

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
                item["name"]
                for item in response.json().get("models", [])
                if item.get("name")
            )
        except (httpx.HTTPError, KeyError, TypeError):
            return []

    def _ollama_enabled(self) -> bool:
        cloud_configured = bool(
            self.settings.google_ai_api_key or self.settings.openrouter_api_key
        )
        return self.settings.enable_local_models or not cloud_configured

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
            return any(
                name == model or name.split(":", 1)[0] == base for name in installed
            )

        providers = {
            "ollama": {
                "enabled": self._ollama_enabled(),
                "reachable": bool(installed),
            },
            "openrouter": {
                "enabled": bool(self.settings.openrouter_api_key),
                "chat_models": [
                    self.settings.openrouter_planner_model,
                    self.settings.openrouter_task_model,
                ],
                "embedding_model": self.settings.openrouter_embedding_model,
            },
            "google": {
                "enabled": bool(self.settings.google_ai_api_key),
                "chat_models": [
                    self.settings.google_planner_model,
                    self.settings.google_task_model,
                ],
                "embedding_model": self.settings.google_embedding_model,
            },
        }
        return {
            "reachable": bool(installed)
            or bool(self.settings.openrouter_api_key)
            or bool(self.settings.google_ai_api_key),
            "provider_order": self.settings.providers,
            "last_chat_provider": self.last_chat_provider,
            "last_embedding_provider": self.last_embedding_provider,
            "providers": providers,
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
        requested_model = model or self.settings.task_model
        errors: list[str] = []
        for provider in self.settings.providers:
            try:
                if provider == "ollama" and self._ollama_enabled():
                    content = await self._ollama_chat(
                        requested_model, prompt, system, schema, temperature
                    )
                elif provider == "openrouter" and self.settings.openrouter_api_key:
                    content = await self._openrouter_chat(
                        requested_model, prompt, system, schema, temperature
                    )
                elif provider == "google" and self.settings.google_ai_api_key:
                    content = await self._google_chat(
                        requested_model, prompt, system, schema, temperature
                    )
                else:
                    continue
                self.last_chat_provider = provider
                return self._validated(content, schema)
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                logger.warning("Chat provider %s failed: %s", provider, exc)
                errors.append(f"{provider}:{type(exc).__name__}")
        detail = ", ".join(errors) or "no provider is enabled"
        raise ModelUnavailable(f"All configured model providers failed ({detail})")

    async def _ollama_chat(
        self,
        model: str,
        prompt: str,
        system: str,
        schema: type[T] | None,
        temperature: float,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": temperature},
        }
        if schema:
            payload["format"] = schema.model_json_schema()
        response = await self._client.post("/api/chat", json=payload)
        if (
            response.status_code == 404
            and self.settings.fallback_chat_model
            and model != self.settings.fallback_chat_model
        ):
            payload["model"] = self.settings.fallback_chat_model
            response = await self._client.post("/api/chat", json=payload)
        response.raise_for_status()
        return str(response.json()["message"]["content"])

    async def _openrouter_chat(
        self,
        requested_model: str,
        prompt: str,
        system: str,
        schema: type[T] | None,
        temperature: float,
    ) -> str:
        model = self._mapped_chat_model(
            requested_model,
            self.settings.openrouter_planner_model,
            self.settings.openrouter_task_model,
        )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
        response = await self._openrouter_client.post(
            "/chat/completions", json=payload, headers=self._openrouter_headers()
        )
        if (
            response.status_code in {404, 408, 409, 429, 500, 502, 503, 504}
            and model == self.settings.openrouter_task_model
            and model != self.settings.openrouter_planner_model
        ):
            logger.warning(
                "OpenRouter task model %s returned %s; retrying with %s",
                model,
                response.status_code,
                self.settings.openrouter_planner_model,
            )
            payload["model"] = self.settings.openrouter_planner_model
            response = await self._openrouter_client.post(
                "/chat/completions", json=payload, headers=self._openrouter_headers()
            )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])

    async def _google_chat(
        self,
        requested_model: str,
        prompt: str,
        system: str,
        schema: type[T] | None,
        temperature: float,
    ) -> str:
        model = self._mapped_chat_model(
            requested_model,
            self.settings.google_planner_model,
            self.settings.google_task_model,
        )
        generation: dict[str, Any] = {"temperature": temperature}
        if schema:
            generation.update(
                {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema.model_json_schema(),
                }
            )
        response = await self._google_client.post(
            f"/models/{model}:generateContent",
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": generation,
            },
            headers={"x-goog-api-key": self.settings.google_ai_api_key},
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(str(part.get("text", "")) for part in parts)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        errors: list[str] = []
        for provider in self.settings.providers:
            try:
                if provider == "ollama" and self._ollama_enabled():
                    vectors = await self._ollama_embed(texts)
                elif provider == "openrouter" and self.settings.openrouter_api_key:
                    vectors = await self._openrouter_embed(texts)
                elif provider == "google" and self.settings.google_ai_api_key:
                    vectors = await self._google_embed(texts)
                else:
                    continue
                self.last_embedding_provider = provider
                return vectors
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                logger.warning("Embedding provider %s failed: %s", provider, exc)
                errors.append(f"{provider}:{type(exc).__name__}")
        detail = ", ".join(errors) or "no provider is enabled"
        raise ModelUnavailable(f"All configured embedding providers failed ({detail})")

    async def _ollama_embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.settings.embedding_model, "input": texts}
        response = await self._client.post("/api/embed", json=payload)
        if (
            response.status_code == 404
            and self.settings.fallback_embedding_model
            and payload["model"] != self.settings.fallback_embedding_model
        ):
            payload["model"] = self.settings.fallback_embedding_model
            response = await self._client.post("/api/embed", json=payload)
        response.raise_for_status()
        return response.json()["embeddings"]

    async def _openrouter_embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._openrouter_client.post(
            "/embeddings",
            json={
                "model": self.settings.openrouter_embedding_model,
                "input": texts,
                "encoding_format": "float",
            },
            headers=self._openrouter_headers(),
        )
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda item: item["index"])
        return [row["embedding"] for row in rows]

    async def _google_embed(self, texts: list[str]) -> list[list[float]]:
        model = self.settings.google_embedding_model
        response = await self._google_client.post(
            f"/models/{model}:batchEmbedContents",
            json={
                "requests": [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": text}]},
                    }
                    for text in texts
                ]
            },
            headers={"x-goog-api-key": self.settings.google_ai_api_key},
        )
        response.raise_for_status()
        return [item["values"] for item in response.json()["embeddings"]]

    def _openrouter_headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "X-Title": self.settings.openrouter_app_name,
        }
        if self.settings.openrouter_site_url:
            headers["HTTP-Referer"] = self.settings.openrouter_site_url
        return headers

    def _mapped_chat_model(
        self, requested_model: str, planner_model: str, task_model: str
    ) -> str:
        if requested_model == self.settings.planner_model:
            return planner_model
        return task_model

    @staticmethod
    def _validated(content: str, schema: type[T] | None) -> str | T:
        if not schema:
            return content
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        return schema.model_validate(json.loads(cleaned))
