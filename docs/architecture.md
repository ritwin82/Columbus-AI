# TravelMind AI architecture

## Request flow

1. FastAPI validates the trip request.
2. The intent agent extracts typed preferences.
3. Hybrid RAG combines Qdrant semantic search, BM25, and Neo4j relationships.
4. Live integrations resolve current place, route, weather, and availability facts.
5. OR-Tools and deterministic rules produce a feasible candidate schedule.
6. The planner writes the itinerary.
7. Validator and reflection agents request targeted repairs when required.

## Storage ownership

- PostgreSQL: users, trips, preferences, approvals, costs, and workflow state
- Qdrant: document chunks and memory embeddings
- OpenSearch: BM25 documents and exact-match fields
- Neo4j: destinations, attractions, amenities, and relationships
- Redis: ephemeral cache and job state

## Constraints

- Fetch live facts at request time.
- Calculate budgets and schedules deterministically.
- Preserve user-approved activities during partial replanning unless infeasible.
- Retain source and freshness metadata for every retrieved claim.

## Retrieval execution

At runtime, `KnowledgeService` always provides an in-process BM25 channel over the normalized JSONL corpus. In hybrid mode it also queries Qdrant using Ollama `bge-m3` embeddings, OpenSearch multi-field keyword search, and Neo4j destination/topic/entity relationships. Reciprocal-rank fusion combines channel ranks before the optional BGE cross-encoder reranker. Each external channel is isolated so temporary service failure falls back to the remaining evidence instead of failing trip generation.

At index time, every chunk is written to Qdrant and OpenSearch and represented as a `KnowledgeChunk` in Neo4j, connected to `Destination`, `Topic`, `Publisher`, and matching `Place` nodes. Source URL, publisher, licence label, retrieval date, and content identity remain attached through the entire path.

## Travel-domain knowledge graph

Neo4j stores attractions, destinations, restaurants, dietary preferences, hotels,
accessibility features, opening time ranges, festivals, months, and transport stops.
The index build creates `LOCATED_IN`, `NEAR`, `SERVES`, `SUITABLE_FOR`,
`OPEN_DURING`, `OCCURS_IN`, and `CONNECTS_TO` relationships. Restaurant and hotel
proximity is destination-level prototype evidence and is labelled as such; it must
be replaced by measured walking or road distance before production use.

During itinerary generation, the planner asks Neo4j for candidate-attraction
scores based on destination, vegetarian requirements, wheelchair requirements,
travel month, nearby accommodation and restaurants, opening-time data, and public
transport connectivity. These graph scores are added to preference and RAG scores
before route optimization.
