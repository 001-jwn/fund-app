"""Fill price, logo, and news from Finnhub. Never crashes the app.

Live data is stored on the company row. It is never written back into
backend/app/seed/seed_companies.json. holder_count is never set.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import date, timedelta

from app import db as dbmod
from app.db import utcnow
from app.models import Company
from app.services.finnhub import DEFAULT_CACHE_DIR, FinnhubClient

logger = logging.getLogger("fund.live")

_client: FinnhubClient | None = None
_stop = threading.Event()
_thread: threading.Thread | None = None
_refresh_lock = threading.Lock()


def should_fetch_live() -> bool:
    """True when a key is set and live calls are not explicitly turned off."""
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        return False
    flag = os.environ.get("FUN_D_FINNHUB_LIVE", "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    return True


def finnhub_mode_label() -> str:
    return "on" if should_fetch_live() else "off"


def get_client() -> FinnhubClient:
    global _client
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    allow = should_fetch_live()
    if _client is None or _client.api_key != key or _client.allow_live != allow:
        _client = FinnhubClient(
            api_key=key,
            allow_live=allow,
            cache_dir=DEFAULT_CACHE_DIR,
        )
    return _client


def refresh_ticker(ticker: str) -> None:
    """Fetch live fields for one ticker and store non-null values. Never raises."""
    if not should_fetch_live():
        return
    ticker = ticker.strip().upper()
    if dbmod.SessionLocal is None:
        return

    needs_quarter = False
    session = dbmod.SessionLocal()
    try:
        company = session.get(Company, ticker)
        if company is None or company.status != "active":
            return
        needs_quarter = not (company.last_quarter_date or "").strip()
    except Exception:
        logger.exception("Could not read %s before Finnhub refresh", ticker)
        return
    finally:
        session.close()

    today = date.today()
    news_from = (today - timedelta(days=30)).isoformat()
    try:
        with _refresh_lock:
            fields = get_client().card_live_fields(
                ticker,
                news_from,
                today.isoformat(),
                include_earnings=needs_quarter,
            )
    except Exception:
        logger.exception("Finnhub refresh failed for %s", ticker)
        return

    session = dbmod.SessionLocal()
    try:
        company = session.get(Company, ticker)
        if company is None:
            return
        changed = _apply_live_fields(company, fields)
        if changed:
            company.data_updated_at = utcnow()
            session.commit()
    except Exception:
        logger.exception("Could not store Finnhub fields for %s", ticker)
        session.rollback()
    finally:
        session.close()


def _apply_live_fields(company: Company, fields: dict) -> bool:
    """Copy only real values. Never invent, never touch holder_count."""
    changed = False
    price = fields.get("current_price")
    if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0:
        company.current_price = float(price)
        pct = fields.get("price_change_percent")
        company.price_change_percent = (
            float(pct) if isinstance(pct, (int, float)) and not isinstance(pct, bool) else None
        )
        changed = True

    logo = fields.get("logo_url")
    if isinstance(logo, str) and logo.strip():
        company.logo_url = logo.strip()
        changed = True

    headline = fields.get("latest_news_headline")
    if isinstance(headline, str) and headline.strip():
        company.latest_news_headline = headline.strip()
        summary = fields.get("latest_news_summary")
        company.latest_news_summary = summary.strip() if isinstance(summary, str) and summary.strip() else None
        news_date = fields.get("latest_news_date")
        company.latest_news_date = news_date if isinstance(news_date, str) and news_date.strip() else None
        changed = True

    # Seed date wins. Finnhub earnings period is only a fallback.
    if not (company.last_quarter_date or "").strip():
        period = fields.get("last_quarter_date")
        if isinstance(period, str) and period.strip():
            company.last_quarter_date = period.strip()
            changed = True

    return changed


def _active_tickers() -> list[str]:
    if dbmod.SessionLocal is None:
        return []
    session = dbmod.SessionLocal()
    try:
        rows = session.query(Company.ticker).filter(Company.status == "active").order_by(Company.ticker).all()
        return [row[0] for row in rows]
    except Exception:
        logger.exception("Could not list tickers for Finnhub refresh")
        return []
    finally:
        session.close()


def _loop() -> None:
    while not _stop.is_set():
        if not should_fetch_live():
            return
        for ticker in _active_tickers():
            if _stop.is_set() or not should_fetch_live():
                return
            refresh_ticker(ticker)
        # Quotes expire after ~5 minutes. Sleep, then let the cache decide
        # what actually needs a network call.
        _stop.wait(60)


def start_refresher() -> None:
    global _thread
    if not should_fetch_live():
        print("Finnhub: off. Price and news will show as unavailable.", flush=True)
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="finnhub-refresh", daemon=True)
    _thread.start()
    print("Finnhub: on. Live prices and news will fill in in the background.", flush=True)


def stop_refresher() -> None:
    _stop.set()
