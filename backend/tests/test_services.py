import json
from dataclasses import asdict

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.rag.ingestion.pipeline import DocumentChunk
from app.repositories.catalog import CatalogueRepository
from app.services.knowledge import KnowledgeService
from app.services.llm import OllamaGateway


class Answer(BaseModel):
    value: str


async def test_ollama_gateway_models_chat_and_embeddings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": "gemma3:12b"},
                {"name": "bge-m3:latest"},
                {"name": "qwen2.5-coder:3b"},
            ]})
        if request.url.path == "/api/embed":
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
        if json.loads(request.content)["model"] != "qwen2.5-coder:3b":
            return httpx.Response(404, json={"error": "model not found"})
        return httpx.Response(200, json={"message": {"content": '{"value":"ok"}'}})

    gateway = OllamaGateway(
        Settings(
            enable_local_models=True,
            model_provider_order="ollama",
            openrouter_api_key="",
            google_ai_api_key="",
        )
    )
    await gateway._client.aclose()
    gateway._client = httpx.AsyncClient(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    try:
        assert await gateway.health()
        readiness = await gateway.readiness()
        assert readiness["reachable"]
        assert "gemma3:4b" in readiness["missing"]
        result = await gateway.chat(prompt="test", system="test", schema=Answer)
        assert result == Answer(value="ok")
        assert await gateway.embed(["test"]) == [[0.1, 0.2]]
    finally:
        await gateway.close()


async def test_ollama_gateway_uses_embedding_fallback() -> None:
    requested_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requested_models.append(payload["model"])
        if payload["model"] == "bge-m3":
            return httpx.Response(404, json={"error": "model not found"})
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})

    gateway = OllamaGateway(
        Settings(
            enable_local_models=True,
            model_provider_order="ollama",
            openrouter_api_key="",
            google_ai_api_key="",
        )
    )
    await gateway._client.aclose()
    gateway._client = httpx.AsyncClient(
        base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )
    try:
        assert await gateway.embed(["Mamallapuram"]) == [[0.1, 0.2, 0.3]]
        assert requested_models == ["bge-m3", "all-minilm"]
    finally:
        await gateway.close()


async def test_openrouter_supplies_exact_gemma_and_bge_models() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request.url.path, payload["model"]))
        assert request.headers["authorization"] == "Bearer test-openrouter-key"
        if request.url.path == "/chat/completions":
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"value":"cloud"}'}}]},
            )
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.3, 0.4]}]},
        )

    settings = Settings(
        enable_local_models=False,
        model_provider_order="openrouter",
        openrouter_api_key="test-openrouter-key",
    )
    gateway = OllamaGateway(settings)
    await gateway._openrouter_client.aclose()
    gateway._openrouter_client = httpx.AsyncClient(
        base_url="https://openrouter.test", transport=httpx.MockTransport(handler)
    )
    try:
        result = await gateway.chat(
            model=settings.planner_model,
            prompt="test",
            system="test",
            schema=Answer,
        )
        assert result == Answer(value="cloud")
        assert await gateway.embed(["Mamallapuram"]) == [[0.3, 0.4]]
        assert requests == [
            ("/chat/completions", "google/gemma-3-12b-it"),
            ("/embeddings", "baai/bge-m3"),
        ]
    finally:
        await gateway.close()


async def test_google_ai_supplies_chat_and_embedding_fallbacks() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        assert request.headers["x-goog-api-key"] == "test-google-key"
        if request.url.path.endswith(":generateContent"):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": '{"value":"google"}' }]}}
                    ]
                },
            )
        return httpx.Response(200, json={"embeddings": [{"values": [0.5, 0.6]}]})

    settings = Settings(
        enable_local_models=False,
        model_provider_order="google",
        google_ai_api_key="test-google-key",
    )
    gateway = OllamaGateway(settings)
    await gateway._google_client.aclose()
    gateway._google_client = httpx.AsyncClient(
        base_url="https://google.test", transport=httpx.MockTransport(handler)
    )
    try:
        result = await gateway.chat(
            prompt="test", system="test", schema=Answer
        )
        assert result == Answer(value="google")
        assert await gateway.embed(["Chennai"]) == [[0.5, 0.6]]
        assert requested_paths == [
            "/models/gemma-4-26b-a4b-it:generateContent",
            "/models/gemini-embedding-001:batchEmbedContents",
        ]
    finally:
        await gateway.close()


async def test_knowledge_loads_generated_corpus(tmp_path) -> None:
    path = tmp_path / "chunks.jsonl"
    chunk = DocumentChunk(
        "chunk-1", "doc-1", "Shore Temple", "Pallava heritage in Mamallapuram",
        "https://example.test/shore", "Test Tourism", "Mamallapuram", "heritage",
        "test", "2026-09-12",
    )
    path.write_text(json.dumps(asdict(chunk)) + "\n", encoding="utf-8")
    settings = Settings(rag_chunks_path=path, rag_mode="local")
    gateway = OllamaGateway(settings)
    service = KnowledgeService(CatalogueRepository(), settings, gateway)
    try:
        results = await service.search("Pallava Mamallapuram")
        assert results[0].chunk_id == "chunk-1"
        assert service.status()["chunks"] == 1
    finally:
        await service.close()
        await gateway.close()


async def test_knowledge_local_mode_fuses_ollama_vectors(tmp_path) -> None:
    path = tmp_path / "chunks.jsonl"
    chunks = [
        DocumentChunk(
            "temple", "temple", "Shore Temple", "Pallava temple heritage",
            "https://example.test/temple", "Tourism", "Mamallapuram", "heritage",
            "test", "2026-09-12",
        ),
        DocumentChunk(
            "food", "food", "Cafe", "French cafe and pastries",
            "https://example.test/cafe", "Tourism", "Puducherry", "food",
            "test", "2026-09-12",
        ),
    ]
    path.write_text(
        "\n".join(json.dumps(asdict(chunk)) for chunk in chunks) + "\n",
        encoding="utf-8",
    )

    class FakeEmbeddings:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [
                [1.0, 0.0] if "heritage" in text.casefold() else [0.0, 1.0]
                for text in texts
            ]

    settings = Settings(
        rag_chunks_path=path, rag_mode="local", enable_local_models=True
    )
    service = KnowledgeService(CatalogueRepository(), settings, FakeEmbeddings())
    try:
        results = await service.search("heritage", limit=2)
        assert results[0].chunk_id == "temple"
        assert results[0].channels == ["bm25", "vector"]
        assert service.status()["channels"]["vector"] == "ready:local"
    finally:
        await service.close()


async def test_knowledge_external_channels_are_resilient(tmp_path) -> None:
    path = tmp_path / "chunks.jsonl"
    chunk = DocumentChunk(
        "chunk-1", "doc-1", "Museum", "Chennai museum", "", "test", "Chennai",
        "museum", "test", "2026-09-12",
    )
    path.write_text(json.dumps(asdict(chunk)) + "\n", encoding="utf-8")
    settings = Settings(rag_chunks_path=path, rag_mode="hybrid")
    gateway = OllamaGateway(settings)
    service = KnowledgeService(CatalogueRepository(), settings, gateway)

    class FailingQdrant:
        async def search(self, query: str, limit: int):
            raise RuntimeError("offline")

    class FailingSearch:
        def search(self, query: str, limit: int):
            raise RuntimeError("offline")

    class FailingGraph:
        def search_chunk_ids(self, query: str, limit: int):
            raise RuntimeError("offline")

        def close(self):
            return None

    service.qdrant = FailingQdrant()
    service.opensearch = FailingSearch()
    service.graph = FailingGraph()
    try:
        results = await service.search("Chennai museum")
        assert results[0].chunk_id == "chunk-1"
        assert all(
            state.startswith("unavailable")
            for channel, state in service.status()["channels"].items()
            if channel != "bm25"
        )
    finally:
        await service.close()
        await gateway.close()


async def test_knowledge_exposes_graph_candidate_scores(tmp_path) -> None:
    path = tmp_path / "chunks.jsonl"
    chunk = DocumentChunk(
        "chunk-1", "doc-1", "Beach", "Accessible promenade", "", "test",
        "Puducherry", "attraction", "test", "2026-09-12",
    )
    path.write_text(json.dumps(asdict(chunk)) + "\n", encoding="utf-8")
    settings = Settings(rag_chunks_path=path, rag_mode="hybrid")
    gateway = OllamaGateway(settings)
    service = KnowledgeService(CatalogueRepository(), settings, gateway)

    class RankingGraph:
        def candidate_place_scores(self, destination: str, **kwargs):
            assert destination == "Puducherry"
            assert kwargs["vegetarian"] is True
            assert kwargs["wheelchair"] is True
            assert kwargs["month"] == "January"
            return [("PY_PUD_001", 8.0)]

        def close(self):
            return None

    service.graph = RankingGraph()
    try:
        scores = await service.candidate_place_scores(
            "Puducherry",
            dietary=["vegetarian"],
            accessibility=["wheelchair"],
            month="January",
        )
        assert scores == {"PY_PUD_001": 8.0}
    finally:
        await service.close()
        await gateway.close()
