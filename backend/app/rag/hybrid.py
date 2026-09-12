"""Hybrid retrieval with lexical, vector, and graph signals."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.rag.ingestion.pipeline import DocumentChunk


@dataclass(slots=True)
class SearchHit:
    chunk: DocumentChunk
    score: float
    channels: tuple[str, ...]


class VectorSearch(Protocol):
    async def __call__(self, query: str, limit: int) -> list[tuple[str, float]]: ...


class GraphSearch(Protocol):
    async def __call__(self, query: str, limit: int) -> list[str]: ...


class KeywordSearch(Protocol):
    async def __call__(self, query: str, limit: int) -> list[tuple[str, float]]: ...


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)


class HybridRetriever:
    def __init__(
        self,
        chunks: list[DocumentChunk],
        *,
        vector_search: VectorSearch | None = None,
        keyword_search: KeywordSearch | None = None,
        graph_search: GraphSearch | None = None,
    ) -> None:
        self.chunks = {chunk.id: chunk for chunk in chunks}
        self.vector_search = vector_search
        self.external_keyword_search = keyword_search
        self.graph_search = graph_search
        self._term_frequency = {key: Counter(_tokens(value.content)) for key, value in self.chunks.items()}
        self._document_frequency = Counter(
            token for frequencies in self._term_frequency.values() for token in frequencies
        )

    def keyword_search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        query_tokens = _tokens(query)
        count = max(1, len(self.chunks))
        scored: list[tuple[str, float]] = []
        for chunk_id, frequencies in self._term_frequency.items():
            score = 0.0
            length = max(1, sum(frequencies.values()))
            for token in query_tokens:
                tf = frequencies[token] / length
                idf = math.log(1 + count / (1 + self._document_frequency[token]))
                score += tf * idf
            if score:
                scored.append((chunk_id, score))
        return sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]

    async def search(self, query: str, *, limit: int = 8) -> list[SearchHit]:
        channels: dict[str, list[tuple[str, float]]] = {
            "bm25": self.keyword_search(query, limit=limit * 3)
        }
        if self.external_keyword_search:
            channels["opensearch"] = await self.external_keyword_search(query, limit * 3)
        if self.vector_search:
            channels["vector"] = await self.vector_search(query, limit * 3)
        if self.graph_search:
            graph_ids = await self.graph_search(query, limit * 3)
            channels["graph"] = [(chunk_id, 1.0) for chunk_id in graph_ids]

        fused: defaultdict[str, float] = defaultdict(float)
        matched_by: defaultdict[str, set[str]] = defaultdict(set)
        for channel, results in channels.items():
            for rank, (chunk_id, _) in enumerate(results, start=1):
                if chunk_id in self.chunks:
                    fused[chunk_id] += 1 / (60 + rank)
                    matched_by[chunk_id].add(channel)

        hits = [
            SearchHit(self.chunks[chunk_id], score, tuple(sorted(matched_by[chunk_id])))
            for chunk_id, score in fused.items()
        ]
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


async def rerank(
    query: str,
    hits: list[SearchHit],
    scorer: Callable[[str, list[str]], Awaitable[list[float]]] | None = None,
) -> list[SearchHit]:
    if not scorer or not hits:
        return hits
    scores = await scorer(query, [hit.chunk.content for hit in hits])
    return [
        hit for _, hit in sorted(zip(scores, hits), key=lambda pair: pair[0], reverse=True)
    ]
