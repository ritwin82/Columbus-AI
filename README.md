# TravelMind AI

Agentic, multimodal travel intelligence for the Chennai–Mamallapuram–Puducherry circuit. The backend generates grounded, budget-aware itineraries, validates them with deterministic rules, and supports versioned partial replanning.

## Repository layout

- `backend/` — FastAPI application, LangGraph workflow, agents, RAG, integrations, and domain logic
- `frontend/` — web client placeholder
- `data/` — source registry and local ingestion areas (large/generated data is ignored)
- `models/` — model configuration; model weights are not committed
- `infra/` — local infrastructure configuration
- `scripts/` — developer, ingestion, and evaluation commands
- `tests/` — integration and end-to-end tests
- `docs/` — architecture, data governance, and API documentation

## Local model stack

- Planner/reflection: Gemma 3 12B Instruct (Q4)
- Task SLM: Gemma 3 4B Instruct (Q4)
- Chat fallback: Qwen 2.5 Coder 3B when either Gemma tag is unavailable
- Embeddings: BAAI/bge-m3, with `all-minilm` as the lightweight Ollama fallback
- Reranker: BAAI/bge-reranker-v2-m3

## Data stack

- Vector retrieval: Qdrant
- Keyword retrieval: OpenSearch/BM25
- Knowledge graph: Neo4j
- Relational state: PostgreSQL
- Cache/jobs: Redis

See `docs/architecture.md` for component boundaries.

## Implemented backend capabilities

- Typed trip, place, itinerary, citation, weather, budget, and validation contracts
- Local Ollama gateway with schema-constrained responses plus automatic chat and embedding fallbacks
- Tamil/English/mixed-language intent and preference extraction with an offline fallback
- HTML/PDF/CSV ingestion, cleaning, provenance retention, and topic-aware chunking
- Hybrid retrieval core with BM25-style lexical search, reciprocal-rank fusion, and reranking hook
- Qdrant, OpenSearch, and Neo4j production index adapters
- Google Places, Google Routes, OpenWeather, and deterministic demo providers
- Preference-aware candidate scoring and optional OR-Tools route ordering
- Deterministic schedule, budget, opening-window, overlap, and weather validation
- LangGraph workflow with bounded reflection and repair
- Long-term preference controls, itinerary version history, and locked-activity replanning
- PostgreSQL/SQLite JSON persistence adapter plus an in-memory test repository
- Static 50-property hotel catalogue with budget/accessibility filtering and itinerary recommendations
- Travel-domain Neo4j graph whose dietary, accessibility, and seasonal relationships affect planner ranking

The `frontend/` placeholder is intentionally not implemented.

## Quick start

1. Copy `.env.example` to `.env`.
2. Install Ollama and pull the models:

   ```powershell
   ollama pull gemma3:12b
   ollama pull gemma3:4b
   ollama pull bge-m3
   ```

   On Windows, after installing Ollama, the equivalent checked setup is:

   ```powershell
   .\scripts\setup_ollama.ps1 -PullModels
   ```

3. Create and activate a Python 3.11+ virtual environment.
4. Install the backend:

   ```powershell
   pip install -e ".\backend[dev,ingestion]"
   ```

5. Start the supporting services:

   ```powershell
   docker compose -f infra/docker-compose.yml up -d
   ```

6. Start the API from `backend/`:

   ```powershell
   uvicorn app.main:app --reload
   ```

Open `http://localhost:8000/docs` for the generated OpenAPI interface.

By default, `USE_MOCK_PROVIDERS=true`, so itinerary generation works without Google or OpenWeather keys. Set it to `false` after supplying API keys. `ENABLE_LOCAL_MODELS` controls Ollama independently from external APIs. Set `PERSISTENCE_BACKEND=postgres` to use PostgreSQL instead of ephemeral memory.

`RAG_MODE=local` uses the generated corpus with in-process BM25 and, when local models are enabled, Ollama cosine semantic search. Set `RAG_MODE=hybrid` after Qdrant, OpenSearch, and Neo4j are running and `scripts/build_indexes.py` has completed. Hybrid mode fuses local BM25, OpenSearch, Qdrant embeddings, and Neo4j graph matches; an unavailable Qdrant channel falls back to local semantic search and every other unavailable channel degrades independently.

## API highlights

```text
GET    /health
GET    /api/v1/status
POST   /api/v1/intent
GET    /api/v1/knowledge/search
GET    /api/v1/hotels/search
POST   /api/v1/trips/generate
GET    /api/v1/trips/{trip_id}
GET    /api/v1/trips/{trip_id}/versions
POST   /api/v1/trips/{trip_id}/replan
GET    /api/v1/users/{user_id}/preferences
DELETE /api/v1/users/{user_id}/preferences
```

## Ingest an approved source

Place a source inside `data/raw/`, then run:

```powershell
python scripts/ingest_sources.py data/raw/pdf/guide.pdf `
  --source-id official-guide-1 `
  --publisher "Tourism Department" `
  --source-url "https://example.gov/guide.pdf" `
  --license "verify-before-use"
```

Build the external indexes after Ollama and the infrastructure services are running:

```powershell
python scripts/build_indexes.py --chunks data/chunks/chunks.jsonl
```

Import the user-owned JSON corpus without changing its original files:

```powershell
python scripts/import_rag_data.py --source-dir "C:\path\to\RAG_DATA"
```

Refresh the bounded official-site corpus (robots-aware, same-domain, HTML-only):

```powershell
python scripts/collect_official_sources.py --max-pages-per-site 3
```

The crawl writes a source-by-source audit trail to `data/sources/crawl_manifest.jsonl`. Public availability is not treated as a reuse licence; every chunk retains its source URL, publisher, retrieval date, and a review-required licence label.

## Verification

```powershell
pytest backend/tests
ruff check backend scripts
python scripts/evaluate_itineraries.py
```

Demo catalogue entries are explicitly labelled as development fixtures. Replace them with reviewed, properly licensed source records before presenting results as verified travel information.
