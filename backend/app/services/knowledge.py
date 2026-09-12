"""Knowledge search facade with resilient local and production retrieval."""

from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.rag.hybrid import HybridRetriever
from app.rag.hybrid import rerank as rerank_hits
from app.rag.ingestion.pipeline import DocumentChunk
from app.repositories.catalog import CatalogueRepository
from app.repositories.retrieval import Neo4jKnowledgeGraph, OpenSearchIndex, QdrantIndex
from app.services.llm import OllamaGateway


class KnowledgeHit(BaseModel):
    chunk_id: str
    title: str
    content: str
    location: str
    topic: str
    source_url: str
    publisher: str
    score: float
    channels: list[str]


class KnowledgeService:
    def __init__(
        self,
        catalogue: CatalogueRepository,
        settings: Settings,
        llm: OllamaGateway,
        reranker: Any = None,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.reranker = reranker
        self.channel_health: dict[str, str] = {"bm25": "ready"}
        chunks = self._load_chunks(settings.rag_chunks_path)
        if not chunks:
            chunks = self._catalogue_chunks(catalogue)
        self._chunks = chunks
        self._local_vectors: list[list[float]] | None = None
        self._vector_lock = asyncio.Lock()

        vector_search = None
        keyword_search = None
        graph_search = None
        self.qdrant: QdrantIndex | None = None
        self.opensearch: OpenSearchIndex | None = None
        self.graph: Neo4jKnowledgeGraph | None = None
        mode = settings.rag_mode.casefold()
        if mode in {"hybrid", "auto"}:
            timeout = settings.rag_external_timeout_seconds
            self.qdrant = QdrantIndex(
                settings.qdrant_url, llm, settings.rag_collection, timeout
            )
            self.opensearch = OpenSearchIndex(
                settings.opensearch_url, settings.rag_index_name, timeout
            )
            self.graph = Neo4jKnowledgeGraph(
                settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password
            )
            vector_search = self._vector_search
            keyword_search = self._keyword_search
            graph_search = self._graph_search
            self.channel_health.update(
                {"vector": "configured", "opensearch": "configured", "graph": "configured"}
            )
        elif mode == "local" and settings.enable_local_models:
            vector_search = self._local_vector_search
            self.channel_health["vector"] = "configured:local"

        self.retriever = HybridRetriever(
            chunks,
            vector_search=vector_search,
            keyword_search=keyword_search,
            graph_search=graph_search,
        )

    @staticmethod
    def _catalogue_chunks(catalogue: CatalogueRepository) -> list[DocumentChunk]:
        return [
            DocumentChunk(
                id=f"place:{place.id}",
                document_id=place.id,
                title=place.name,
                content=(
                    f"{place.name} is in {place.destination}. {place.description} "
                    f"Categories: {', '.join(place.categories)}. Indoor: {place.indoor}. "
                    f"Accessibility: {', '.join(place.accessibility) or 'unknown'}."
                ),
                source_url=str(place.citations[0].source_url) if place.citations else "",
                publisher=(
                    place.citations[0].publisher if place.citations else "development fixture"
                ),
                location=place.destination,
                topic="attraction",
                license="development fixture",
                retrieved_at=datetime.now(UTC).date().isoformat(),
            )
            for place in catalogue.all()
        ]

    @staticmethod
    def _load_chunks(configured_path: Path) -> list[DocumentChunk]:
        project_root = Path(__file__).resolve().parents[3]
        path = configured_path if configured_path.is_absolute() else project_root / configured_path
        if not path.exists():
            return []
        chunks: list[DocumentChunk] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                chunks.append(DocumentChunk(**json.loads(line)))
            except (TypeError, json.JSONDecodeError):
                continue
        return chunks

    async def _vector_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        if not self.qdrant:
            return []
        try:
            results = await self.qdrant.search(query, limit)
            self.channel_health["vector"] = "ready"
            return results
        except Exception as exc:  # noqa: BLE001 - optional provider boundary
            self.channel_health["vector"] = f"unavailable:{type(exc).__name__}"
            if self.settings.enable_local_models:
                results = await self._local_vector_search(query, limit)
                if results:
                    self.channel_health["vector"] = "ready:local-fallback"
                return results
            return []

    async def _local_vector_search(
        self, query: str, limit: int
    ) -> list[tuple[str, float]]:
        try:
            if self._local_vectors is None:
                async with self._vector_lock:
                    if self._local_vectors is None:
                        self._local_vectors = await self.llm.embed(
                            [chunk.content for chunk in self._chunks]
                        )
            query_vector = (await self.llm.embed([query]))[0]
            query_norm = math.sqrt(sum(value * value for value in query_vector))
            scored: list[tuple[str, float]] = []
            for chunk, vector in zip(self._chunks, self._local_vectors):
                vector_norm = math.sqrt(sum(value * value for value in vector))
                denominator = query_norm * vector_norm
                score = (
                    sum(left * right for left, right in zip(query_vector, vector)) / denominator
                    if denominator
                    else 0.0
                )
                scored.append((chunk.id, score))
            self.channel_health["vector"] = "ready:local"
            return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]
        except Exception as exc:  # noqa: BLE001 - local model boundary
            self.channel_health["vector"] = f"unavailable:{type(exc).__name__}"
            return []

    async def _keyword_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        if not self.opensearch:
            return []
        try:
            results = await asyncio.to_thread(self.opensearch.search, query, limit)
            self.channel_health["opensearch"] = "ready"
            return results
        except Exception as exc:  # noqa: BLE001 - optional provider boundary
            self.channel_health["opensearch"] = f"unavailable:{type(exc).__name__}"
            return []

    async def _graph_search(self, query: str, limit: int) -> list[str]:
        if not self.graph:
            return []
        try:
            results = await asyncio.to_thread(self.graph.search_chunk_ids, query, limit)
            self.channel_health["graph"] = "ready"
            return results
        except Exception as exc:  # noqa: BLE001 - optional provider boundary
            self.channel_health["graph"] = f"unavailable:{type(exc).__name__}"
            return []

    async def candidate_place_scores(
        self,
        destination: str,
        *,
        dietary: list[str],
        accessibility: list[str],
        month: str,
    ) -> dict[str, float]:
        if not self.graph:
            return {}
        vegetarian = any("vegetarian" in item.casefold() for item in dietary)
        wheelchair = any("wheelchair" in item.casefold() for item in accessibility)
        try:
            rows = await asyncio.to_thread(
                self.graph.candidate_place_scores,
                destination,
                vegetarian=vegetarian,
                wheelchair=wheelchair,
                month=month,
            )
            self.channel_health["graph_candidates"] = "ready"
            return dict(rows)
        except Exception as exc:  # noqa: BLE001 - optional provider boundary
            self.channel_health["graph_candidates"] = f"unavailable:{type(exc).__name__}"
            return {}

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.settings.rag_mode,
            "chunks": len(self.retriever.chunks),
            "channels": dict(self.channel_health),
            "reranker": bool(self.reranker),
        }

    async def close(self) -> None:
        if self.graph:
            await asyncio.to_thread(self.graph.close)

    async def search(self, query: str, limit: int = 8) -> list[KnowledgeHit]:
        hits = await self.retriever.search(query, limit=max(limit, 20))
        if self.reranker:
            hits = await rerank_hits(query, hits, self.reranker.score)
        hits = hits[:limit]
        return [
            KnowledgeHit(
                chunk_id=hit.chunk.id,
                title=hit.chunk.title,
                content=hit.chunk.content,
                location=hit.chunk.location,
                topic=hit.chunk.topic,
                source_url=hit.chunk.source_url,
                publisher=hit.chunk.publisher,
                score=hit.score,
                channels=list(hit.channels),
            )
            for hit in hits
        ]
