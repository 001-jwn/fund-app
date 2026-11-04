"""fun(d) API. Run from the backend folder:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db as dbmod
from app.db import configure_engine, init_db
from app.routers import cards, matches, onboarding, swipes
from app.schemas import HealthOut
from app.services.live import finnhub_mode_label, start_refresher, stop_refresher

# backend/app/main.py -> repository root
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load again in case the process environment changed after import.
    load_dotenv(REPO_ROOT / ".env", override=False)
    configure_engine()
    init_db()
    from app.seed.load_seed import load_seed

    count = load_seed()
    print(f"fun(d) ready. Loaded {count} companies.", flush=True)
    start_refresher()
    yield
    stop_refresher()
    if dbmod.ENGINE is not None:
        dbmod.ENGINE.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="fun(d)", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(onboarding.router)
    app.include_router(cards.router)
    app.include_router(swipes.router)
    app.include_router(matches.router)

    @app.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(status="ok", finnhub=finnhub_mode_label())

    return app


app = create_app()
