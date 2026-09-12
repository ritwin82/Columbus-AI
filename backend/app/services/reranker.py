"""Lazy local cross-encoder reranker."""

from __future__ import annotations

import asyncio


class LocalReranker:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    async def score(self, query: str, documents: list[str]) -> list[float]:
        def predict() -> list[float]:
            model = self._load()
            values = model.predict([[query, document] for document in documents])
            return [float(value) for value in values]

        return await asyncio.to_thread(predict)
