"""Production adapters for Qdrant, OpenSearch, and Neo4j."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.models.schemas import Hotel, Place
from app.rag.ingestion.pipeline import DocumentChunk
from app.services.llm import OllamaGateway


class QdrantIndex:
    def __init__(
        self,
        url: str,
        embeddings: OllamaGateway,
        collection: str = "travel_knowledge",
        timeout: float = 5.0,
    ) -> None:
        from qdrant_client import AsyncQdrantClient

        self.client = AsyncQdrantClient(url=url, timeout=max(1, int(timeout)))
        self.embeddings = embeddings
        self.collection = collection

    async def index(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0
        from qdrant_client.models import Distance, PointStruct, VectorParams

        vectors = await self.embeddings.embed([chunk.content for chunk in chunks])
        collections = await self.client.get_collections()
        names = {item.name for item in collections.collections}
        if self.collection not in names:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=len(vectors[0]), distance=Distance.COSINE),
            )
        points = [
            PointStruct(
                id=str(uuid5(NAMESPACE_URL, chunk.id)),
                vector=vector,
                payload={**asdict(chunk), "chunk_id": chunk.id},
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        await self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return len(points)

    async def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        vector = (await self.embeddings.embed([query]))[0]
        response = await self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        return [
            (str(point.payload.get("chunk_id")), float(point.score))
            for point in response.points if point.payload
        ]


class OpenSearchIndex:
    def __init__(
        self, url: str, index_name: str = "travel-knowledge", timeout: float = 5.0
    ) -> None:
        from opensearchpy import OpenSearch

        self.client = OpenSearch(
            hosts=[url], timeout=timeout, max_retries=0, retry_on_timeout=False
        )
        self.index_name = index_name

    def index(self, chunks: Iterable[DocumentChunk]) -> int:
        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(
                index=self.index_name,
                body={
                    "settings": {"number_of_replicas": 0},
                    "mappings": {
                        "properties": {
                            "content": {"type": "text"},
                            "title": {"type": "text"},
                            "location": {"type": "keyword"},
                            "topic": {"type": "keyword"},
                        }
                    }
                },
            )
        count = 0
        for chunk in chunks:
            self.client.index(index=self.index_name, id=chunk.id, body=asdict(chunk), refresh=False)
            count += 1
        self.client.indices.refresh(index=self.index_name)
        return count

    def search(self, query: str, limit: int = 20) -> list[tuple[str, float]]:
        response = self.client.search(
            index=self.index_name,
            size=limit,
            body={"query": {"multi_match": {"query": query, "fields": ["title^2", "content", "topic"]}}},
        )
        return [(hit["_id"], float(hit["_score"])) for hit in response["hits"]["hits"]]


class Neo4jKnowledgeGraph:
    def __init__(self, uri: str, user: str, password: str) -> None:
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self.driver.close()

    def upsert_places(
        self,
        places: Iterable[Place],
        accessibility_overrides: dict[str, list[str]] | None = None,
    ) -> int:
        overrides = accessibility_overrides or {}
        rows = [
            {
                "id": place.id,
                "name": place.name,
                "destination": place.destination,
                "categories": place.categories,
                "latitude": place.latitude,
                "longitude": place.longitude,
                "accessibility": place.accessibility,
                "suitable_for": sorted(
                    set(place.accessibility) | set(overrides.get(place.id, []))
                ),
                "opening_time": place.opening_time.isoformat(),
                "closing_time": place.closing_time.isoformat(),
            }
            for place in places
        ]
        query = """
        UNWIND $rows AS row
        MERGE (p:Place:Attraction {id: row.id})
        SET p += row
        MERGE (d:Destination {name: row.destination})
        MERGE (p)-[:LOCATED_IN]->(d)
        MERGE (window:TimeRange {id: row.id + ':' + row.opening_time + '-' + row.closing_time})
        SET window.opens = row.opening_time, window.closes = row.closing_time
        MERGE (p)-[:OPEN_DURING]->(window)
        FOREACH (feature IN row.suitable_for |
          MERGE (need:AccessibilityFeature {name: feature})
          MERGE (p)-[:SUITABLE_FOR]->(need)
        )
        """
        with self.driver.session() as session:
            session.run(query, rows=rows).consume()
        return len(rows)

    def upsert_hotels(self, hotels: Iterable[Hotel]) -> int:
        rows = [
            {
                "id": hotel.id,
                "name": hotel.name,
                "destination": hotel.destination,
                "area": hotel.area,
                "type": hotel.accommodation_type,
                "price_tier": hotel.price_tier,
                "price_from_inr": float(hotel.estimated_price_from_inr),
                "price_to_inr": float(hotel.estimated_price_to_inr),
                "amenities": hotel.amenities,
                "accessibility": hotel.accessibility,
                "catalogue_rank": hotel.catalogue_rank,
            }
            for hotel in hotels
        ]
        query = """
        UNWIND $rows AS row
        MERGE (h:Hotel {id: row.id}) SET h += row
        MERGE (d:Destination {name: row.destination})
        MERGE (h)-[:LOCATED_IN]->(d)
        """
        if rows:
            with self.driver.session() as session:
                session.run(query, rows=rows).consume()
        return len(rows)

    def upsert_restaurants(self, rows: list[dict[str, Any]]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (r:Restaurant {id: row.id}) SET r += row
        MERGE (d:Destination {name: row.destination})
        MERGE (r)-[:LOCATED_IN]->(d)
        FOREACH (diet IN row.dietary |
          MERGE (preference:DietaryPreference {name: diet})
          MERGE (r)-[:SERVES]->(preference)
        )
        """
        if rows:
            with self.driver.session() as session:
                session.run(query, rows=rows).consume()
        return len(rows)

    def upsert_festivals(self, rows: list[dict[str, Any]]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (f:Festival {id: row.id}) SET f.name = row.name, f.tags = row.tags
        MERGE (d:Destination {name: row.destination})
        MERGE (f)-[:HELD_IN]->(d)
        FOREACH (month IN row.months |
          MERGE (m:Month {name: month})
          MERGE (f)-[:OCCURS_IN]->(m)
        )
        """
        if rows:
            with self.driver.session() as session:
                session.run(query, rows=rows).consume()
        return len(rows)

    def upsert_transport_stops(self, rows: list[dict[str, Any]]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (stop:TransportStop {id: row.id}) SET stop += row
        MERGE (d:Destination {name: row.destination})
        MERGE (stop)-[:LOCATED_IN]->(d)
        """
        if rows:
            with self.driver.session() as session:
                session.run(query, rows=rows).consume()
        return len(rows)

    def link_domain_entities(self, basis: str) -> dict[str, int]:
        queries = {
            "hotel_near_attraction": """
                MATCH (h:Hotel)-[:LOCATED_IN]->(d:Destination)<-[:LOCATED_IN]-(a:Attraction)
                MERGE (h)-[rel:NEAR]->(a) SET rel.basis = $basis
                RETURN count(rel) AS count
            """,
            "restaurant_near_attraction": """
                MATCH (r:Restaurant)-[:LOCATED_IN]->(d:Destination)<-[:LOCATED_IN]-(a:Attraction)
                MERGE (r)-[rel:NEAR]->(a) SET rel.basis = $basis
                RETURN count(rel) AS count
            """,
            "stop_connects_attraction": """
                MATCH (stop:TransportStop)-[:LOCATED_IN]->(d:Destination)<-[:LOCATED_IN]-(a:Attraction)
                MERGE (stop)-[rel:CONNECTS_TO]->(a) SET rel.basis = $basis
                RETURN count(rel) AS count
            """,
        }
        counts: dict[str, int] = {}
        with self.driver.session() as session:
            for name, query in queries.items():
                record = session.run(query, basis=basis).single()
                counts[name] = int(record["count"]) if record else 0
        return counts

    def candidate_place_scores(
        self,
        destination: str,
        *,
        vegetarian: bool = False,
        wheelchair: bool = False,
        month: str = "",
        limit: int = 50,
    ) -> list[tuple[str, float]]:
        query = """
        MATCH (a:Attraction)-[:LOCATED_IN]->(d:Destination {name: $destination})
        OPTIONAL MATCH (a)<-[:NEAR]-(r:Restaurant)-[:SERVES]->(diet:DietaryPreference)
        OPTIONAL MATCH (a)<-[:NEAR]-(hotel:Hotel)
        OPTIONAL MATCH (a)-[:SUITABLE_FOR]->(access:AccessibilityFeature)
        OPTIONAL MATCH (a)-[:OPEN_DURING]->(window:TimeRange)
        OPTIONAL MATCH (a)<-[:CONNECTS_TO]-(stop:TransportStop)
        OPTIONAL MATCH (festival:Festival)-[:HELD_IN]->(d)
        OPTIONAL MATCH (festival)-[:OCCURS_IN]->(eventMonth:Month)
        WITH a,
             collect(DISTINCT toLower(diet.name)) AS diets,
             count(DISTINCT r) AS nearbyRestaurants,
             count(DISTINCT hotel) AS nearbyHotels,
             collect(DISTINCT toLower(access.name)) AS accessFeatures,
             count(DISTINCT window) AS openingWindows,
             count(DISTINCT stop) AS transportStops,
             collect(DISTINCT toLower(eventMonth.name)) AS eventMonths
        WITH a,
             CASE WHEN $vegetarian AND any(
                    x IN diets WHERE x IN ['vegetarian', 'vegetarian options']
                  )
                  THEN 3 ELSE 0 END +
             CASE WHEN NOT $vegetarian AND nearbyRestaurants > 0
                  THEN 0.5 ELSE 0 END +
             CASE WHEN nearbyHotels > 0 THEN 0.5 ELSE 0 END +
             CASE WHEN $wheelchair AND 'wheelchair' IN accessFeatures
                  THEN 4 ELSE 0 END +
             CASE WHEN openingWindows > 0 THEN 0.5 ELSE 0 END +
             CASE WHEN transportStops > 0 THEN 1 ELSE 0 END +
             CASE WHEN toLower($month) IN eventMonths THEN 1 ELSE 0 END AS graphScore
        WITH a, graphScore WHERE graphScore > 0
        RETURN a.id AS id, graphScore AS score
        ORDER BY graphScore DESC, a.id LIMIT $limit
        """
        with self.driver.session() as session:
            return [
                (row["id"], float(row["score"]))
                for row in session.run(
                    query,
                    destination=destination,
                    vegetarian=vegetarian,
                    wheelchair=wheelchair,
                    month=month,
                    limit=limit,
                )
            ]

    def upsert_chunks(self, chunks: Iterable[DocumentChunk]) -> int:
        rows = [asdict(chunk) for chunk in chunks]
        query = """
        UNWIND $rows AS row
        MERGE (c:KnowledgeChunk {id: row.id})
        SET c.document_id = row.document_id,
            c.title = row.title,
            c.content = row.content,
            c.source_url = row.source_url,
            c.publisher = row.publisher,
            c.location = row.location,
            c.topic = row.topic,
            c.license = row.license,
            c.retrieved_at = row.retrieved_at
        MERGE (d:Destination {name: row.location})
        MERGE (t:Topic {name: row.topic})
        MERGE (s:Publisher {name: row.publisher})
        MERGE (c)-[:ABOUT_DESTINATION]->(d)
        MERGE (c)-[:HAS_TOPIC]->(t)
        MERGE (c)-[:PUBLISHED_BY]->(s)
        WITH c, row
        OPTIONAL MATCH (p:Place {id: row.document_id})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END |
          MERGE (c)-[:DESCRIBES]->(p)
        )
        """
        if rows:
            with self.driver.session() as session:
                session.run(query, rows=rows).consume()
        return len(rows)

    def search_chunk_ids(self, text: str, limit: int = 20) -> list[str]:
        tokens = [token.casefold() for token in text.split() if len(token) > 2][:12]
        query = """
        MATCH (c:KnowledgeChunk)
        OPTIONAL MATCH (c)-[:ABOUT_DESTINATION]->(d:Destination)
        OPTIONAL MATCH (c)-[:HAS_TOPIC]->(t:Topic)
        WITH c, d, t,
             size([token IN $tokens WHERE
               toLower(coalesce(c.title, '')) CONTAINS token OR
               toLower(coalesce(c.content, '')) CONTAINS token OR
               toLower(coalesce(d.name, '')) CONTAINS token OR
               toLower(coalesce(t.name, '')) CONTAINS token]) AS matches
        WHERE matches > 0
        RETURN c.id AS id ORDER BY matches DESC LIMIT $limit
        """
        with self.driver.session() as session:
            return [
                row["id"]
                for row in session.run(query, tokens=tokens, limit=limit)
            ]

    def link_nearby(self, maximum_km: float = 3.0) -> int:
        query = """
        MATCH (a:Place), (b:Place)
        WHERE a.id < b.id AND point.distance(
          point({latitude: a.latitude, longitude: a.longitude}),
          point({latitude: b.latitude, longitude: b.longitude})
        ) <= $metres
        MERGE (a)-[:NEAR]-(b)
        RETURN count(*) AS count
        """
        with self.driver.session() as session:
            record = session.run(query, metres=maximum_km * 1000).single()
            return int(record["count"]) if record else 0

    def related_place_ids(self, place_id: str, limit: int = 20) -> list[str]:
        query = """
        MATCH (:Place {id: $place_id})-[:NEAR]-(related:Place)
        RETURN related.id AS id LIMIT $limit
        """
        with self.driver.session() as session:
            return [row["id"] for row in session.run(query, place_id=place_id, limit=limit)]
