"""Build Qdrant, OpenSearch, and Neo4j indexes from local curated data."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import get_settings
from app.rag.ingestion.pipeline import DocumentChunk
from app.repositories.catalog import CatalogueRepository
from app.repositories.hotels import HotelRepository
from app.repositories.retrieval import (
    Neo4jKnowledgeGraph,
    OpenSearchIndex,
    QdrantIndex,
)
from app.services.llm import OllamaGateway


async def build(chunks_path: Path) -> None:
    chunks = [
        DocumentChunk(**json.loads(line))
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    settings = get_settings()
    graph_data_path = PROJECT_ROOT / "data" / "processed" / "graph_entities.json"
    graph_data = json.loads(graph_data_path.read_text(encoding="utf-8"))
    gateway = OllamaGateway(settings)
    graph = Neo4jKnowledgeGraph(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    try:
        vector_count = await QdrantIndex(
            settings.qdrant_url,
            gateway,
            settings.rag_collection,
            settings.rag_external_timeout_seconds,
        ).index(chunks)
        keyword_count = OpenSearchIndex(
            settings.opensearch_url,
            settings.rag_index_name,
            settings.rag_external_timeout_seconds,
        ).index(chunks)
        place_count = graph.upsert_places(
            CatalogueRepository().all(),
            graph_data.get("attraction_accessibility", {}),
        )
        hotel_count = graph.upsert_hotels(HotelRepository().all())
        restaurant_count = graph.upsert_restaurants(graph_data.get("restaurants", []))
        festival_count = graph.upsert_festivals(graph_data.get("festivals", []))
        stop_count = graph.upsert_transport_stops(graph_data.get("transport_stops", []))
        chunk_count = graph.upsert_chunks(chunks)
        relation_count = graph.link_nearby()
        domain_relations = graph.link_domain_entities(
            graph_data.get("proximity_basis", "destination-level prototype proximity")
        )
        print(
            f"Indexed vector={vector_count}, keyword={keyword_count}, "
            f"places={place_count}, hotels={hotel_count}, restaurants={restaurant_count}, "
            f"festivals={festival_count}, transport_stops={stop_count}, "
            f"graph_chunks={chunk_count}, attraction_nearby={relation_count}, "
            f"domain_relationships={domain_relations}"
        )
    finally:
        graph.close()
        await gateway.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chunks",
        type=Path,
        default=PROJECT_ROOT / "data" / "chunks" / "chunks.jsonl",
    )
    args = parser.parse_args()
    asyncio.run(build(args.chunks))


if __name__ == "__main__":
    main()
