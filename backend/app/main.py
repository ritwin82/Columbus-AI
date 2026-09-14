"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.container import build_container


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.container = build_container()
    yield
    await application.state.container.close()


app = FastAPI(
    title="TravelMind AI",
    description="Grounded, budget-aware, dynamically adaptable travel planning",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _frontend_directory() -> Path | None:
    candidates = (
        Path(__file__).resolve().parents[2] / "frontend",
        Path("/frontend"),
    )
    return next(
        (candidate for candidate in candidates if (candidate / "index.html").is_file()),
        None,
    )


frontend_directory = _frontend_directory()
if frontend_directory:
    app.mount(
        "/",
        StaticFiles(directory=frontend_directory, html=True),
        name="frontend",
    )
