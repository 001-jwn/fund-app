"""Database setup.

SQLite is the local default. The same models work with PostgreSQL later:
set DATABASE_URL to a postgresql:// URL and no model code has to change.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BACKEND_DIR / "fund.db"

# sqlite3.connect timeout is in seconds. PRAGMA busy_timeout is milliseconds.
SQLITE_CONNECT_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = 30000
# journal_mode=WAL on a brand-new file can raise "database is locked" immediately
# (SQLITE_LOCKED, which busy_timeout does not wait out). Retry those, then move on.
_WAL_RETRY_DELAYS_SECONDS = (0.02, 0.05, 0.1, 0.2)

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


def make_engine(url: str):
    """Create an engine. Two SQLite engines may open the same file."""
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # The background Finnhub thread and request handlers share this file.
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = SQLITE_CONNECT_TIMEOUT_SECONDS
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _record):  # noqa: ANN001
            cursor = conn.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
                _enable_wal(cursor)
            finally:
                cursor.close()

    return engine


def _enable_wal(cursor) -> None:
    """Set WAL. Skip it if the file stays locked, instead of crashing startup."""
    attempts = len(_WAL_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            if attempt == attempts - 1:
                return
            time.sleep(_WAL_RETRY_DELAYS_SECONDS[attempt])


def configure_engine(url: str | None = None):
    """Create the engine. Safe to call again (tests use a fresh database)."""
    global ENGINE, SessionLocal
    url = url or database_url()
    ENGINE = make_engine(url)
    SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)
    return ENGINE


def init_db() -> None:
    # Import models so they register on Base before create_all.
    from app import models  # noqa: F401

    if ENGINE is None:
        configure_engine()
    Base.metadata.create_all(ENGINE)
    _add_missing_company_columns()
    _add_missing_sec_filing_columns()


# Columns added after the first release. create_all does not alter an existing table.
_MISSING_COMPANY_COLUMNS = (
    ("short_name", "TEXT"),
    ("latest_quote_at", "DATETIME"),
    ("latest_news_source", "TEXT"),
    ("latest_news_url", "TEXT"),
    ("latest_news_id", "TEXT"),
    ("latest_news_unix", "FLOAT"),
)


def _add_missing_company_columns() -> None:
    """Add company columns on a SQLite file created before them.

    Do not drop or recreate the table. Rows already in the file stay.
    """
    if ENGINE is None or ENGINE.dialect.name != "sqlite":
        return
    with ENGINE.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(companies)").fetchall()
        if not rows:
            return
        present = {row[1] for row in rows}
        for name, column_type in _MISSING_COMPANY_COLUMNS:
            if name in present:
                continue
            conn.exec_driver_sql(f"ALTER TABLE companies ADD COLUMN {name} {column_type}")


# Columns added for filing-text confirmation. create_all does not alter an existing table.
_MISSING_SEC_FILING_COLUMNS = (
    ("measure", "TEXT"),
    ("figure", "TEXT"),
    ("exhibit_url", "TEXT"),
    ("is_quarter", "BOOLEAN"),
    ("counterparty", "TEXT"),
    ("side", "VARCHAR(16)"),
    ("stage", "VARCHAR(16)"),
    ("asset", "TEXT"),
    ("person", "TEXT"),
    ("role", "TEXT"),
    ("lead_direction", "VARCHAR(16)"),
    ("resigned_or_retired", "BOOLEAN"),
    ("eff_date", "VARCHAR(32)"),
    ("guide_direction", "VARCHAR(16)"),
    ("period_label", "TEXT"),
    ("leaders_json", "TEXT"),
    ("text_outcome", "VARCHAR(24)"),
)


def _add_missing_sec_filing_columns() -> None:
    """Add filing columns on a SQLite file created before text confirmation."""
    if ENGINE is None or ENGINE.dialect.name != "sqlite":
        return
    with ENGINE.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(sec_filings)").fetchall()
        if not rows:
            return
        present = {row[1] for row in rows}
        for name, column_type in _MISSING_SEC_FILING_COLUMNS:
            if name in present:
                continue
            conn.exec_driver_sql(f"ALTER TABLE sec_filings ADD COLUMN {name} {column_type}")


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        configure_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
