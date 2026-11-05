"""Load seed_companies.json into the database.

Interests and why lines come only from each company's `interests` list.
`interest_tags` is ignored. Live fields in the file stay null; this loader
never writes prices, news, or logos, and it never writes the file back.
Running it twice updates curated text and leaves cached live fields alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import db as dbmod
from app.interests import ALLOWED_INTERESTS
from app.models import Company, CompanyInterest

SEED_PATH = Path(__file__).resolve().parent / "seed_companies.json"
ALLOWED = set(ALLOWED_INTERESTS)


def load_seed(path: Path | None = None) -> int:
    path = Path(path) if path is not None else SEED_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    companies = payload.get("companies") or []
    if dbmod.SessionLocal is None:
        raise RuntimeError("Database is not configured")

    # Look up the session factory at call time so tests can swap databases.
    session = dbmod.SessionLocal()
    try:
        for raw in companies:
            _upsert_company(session, raw)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return len(companies)


def _upsert_company(session, raw: dict) -> None:
    ticker = str(raw.get("ticker") or "").strip().upper()
    if not ticker:
        return

    status = str(raw.get("status") or "active").strip().lower()
    company = session.get(Company, ticker)
    if company is None:
        company = Company(
            ticker=ticker,
            company_name=str(raw.get("company_name") or ticker),
            short_name=_text(raw.get("short_name")),
            short_description=_text(raw.get("short_description")),
            current_price=None,
            price_change_percent=None,
            holder_count=None,
            latest_news_headline=None,
            latest_news_summary=None,
            latest_news_date=None,
            quarterly_summary=_text(raw.get("quarterly_summary")),
            last_quarter_date=_text(raw.get("last_quarter_date")),
            logo_url=None,
            status=status,
            data_updated_at=None,
        )
        session.add(company)
        session.flush()
    else:
        # Curated copy only. Do not wipe a cached price, logo, or headline
        # just because the seed file keeps those fields null on purpose.
        company.company_name = str(raw.get("company_name") or company.company_name)
        company.short_name = _text(raw.get("short_name"))
        company.short_description = _text(raw.get("short_description"))
        company.quarterly_summary = _text(raw.get("quarterly_summary"))
        company.last_quarter_date = _text(raw.get("last_quarter_date"))
        company.status = status

    session.query(CompanyInterest).filter(CompanyInterest.ticker == ticker).delete(
        synchronize_session=False
    )

    seen: set[str] = set()
    # ONLY the interests list. interest_tags is not read.
    for item in raw.get("interests") or []:
        if not isinstance(item, dict):
            continue
        interest = str(item.get("interest") or "").strip().lower()
        why_line = str(item.get("why_line") or "").strip()
        if interest not in ALLOWED or interest in seen or not why_line:
            continue
        session.add(CompanyInterest(ticker=ticker, interest=interest, why_line=why_line))
        seen.add(interest)


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    from app.db import configure_engine, init_db

    configure_engine()
    init_db()
    count = load_seed()
    print(f"Loaded {count} companies from {SEED_PATH}")
