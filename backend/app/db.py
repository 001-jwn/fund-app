"""Database setup.

SQLite is the local default. The same models work with PostgreSQL later:
set DATABASE_URL to a postgresql:// URL and no model code has to change.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BACKEND_DIR / "fund.db"

ENGINE = None
SessionLocal = None


def utcnow() -> datetime:
    """Naive UTC timestamp. Portable across SQLite and PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    return "sqlite:///" + DEFAULT_SQLITE_PATH.as_posix()


def configure_engine(url: str | None = None):
    """Create the engine. Safe to call again (tests use a fresh database)."""
    global ENGINE, SessionLocal
    url = url or database_url()
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # The background Finnhub thread and request handlers share this file.
        connect_args["check_same_thread"] = False
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _record):  # noqa: ANN001
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    ENGINE = engine
    SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)
    return ENGINE


def init_db() -> None:
    # Import models so they register on Base before create_all.
    from app import models  # noqa: F401

    if ENGINE is None:
        configure_engine()
    Base.metadata.create_all(ENGINE)


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        configure_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
