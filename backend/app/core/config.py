"""Typed application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    ollama_base_url: str = "http://localhost:11434"
    planner_model: str = "gemma3:12b"
    task_model: str = "gemma3:4b"
    fallback_chat_model: str = "qwen2.5-coder:3b"
    embedding_model: str = "bge-m3"
    fallback_embedding_model: str = "all-minilm"
    model_provider_order: str = "openrouter,google,ollama"
    google_ai_api_key: str = ""
    google_planner_model: str = "gemma-4-26b-a4b-it"
    google_task_model: str = "gemma-4-26b-a4b-it"
    google_embedding_model: str = "gemini-embedding-001"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_planner_model: str = "google/gemma-3-12b-it"
    openrouter_task_model: str = "google/gemma-3-4b-it"
    openrouter_embedding_model: str = "baai/bge-m3"
    openrouter_app_name: str = "TravelMind AI"
    openrouter_site_url: str = ""
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    enable_local_reranker: bool = False
    rag_mode: str = "local"
    rag_chunks_path: Path = Path("data/chunks/chunks.jsonl")
    rag_collection: str = "travel_knowledge"
    rag_index_name: str = "travel-knowledge"
    rag_external_timeout_seconds: float = 2.0

    postgres_url: str = "postgresql+psycopg://travelmind:travelmind@localhost:5432/travelmind"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    opensearch_url: str = "http://localhost:9200"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change-me"

    google_maps_api_key: str = ""
    openweather_api_key: str = ""
    enable_local_models: bool = False
    use_mock_providers: bool = True
    persistence_backend: str = "memory"
    max_reflections: int = 3
    request_timeout_seconds: float = 20

    @property
    def ai_models_enabled(self) -> bool:
        return bool(
            self.enable_local_models
            or self.google_ai_api_key
            or self.openrouter_api_key
        )

    @property
    def providers(self) -> list[str]:
        allowed = {"ollama", "google", "openrouter"}
        return [
            item
            for value in self.model_provider_order.split(",")
            if (item := value.strip().casefold()) in allowed
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
