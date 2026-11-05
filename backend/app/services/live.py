"""Fill price, logo, and news from Finnhub. Never crashes the app.

Live data is stored on the company row. It is never written back into
backend/app/seed/seed_companies.json. holder_count is never set.

A pass fetches every quote first, then every news list, then every profile,
so prices show up before logos. The Finnhub client caches each response on
disk under backend/cache/finnhub, so a restart does not repeat a fresh call
until that cache entry expires. Calls stay about 1.1 seconds apart.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from datetime import date, datetime, timedelta, timezone

from app import db as dbmod
from app.db import utcnow
from app.models import Company
from app.services.finnhub import DEFAULT_CACHE_DIR, FinnhubClient, _price_from_quote
from app.services.news import NO_RECENT_NEWS_SENTINEL, select_company_news

logger = logging.getLogger("fund.live")

_client: FinnhubClient | None = None
_stop = threading.Event()
_thread: threading.Thread | None = None
_refresh_lock = threading.Lock()

# Quotes for every ticker, then news, then logos. Not three calls per ticker.
PHASES = ("quote", "news", "profile")


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


def refresh_passes(tickers: list[str] | None = None, respect_stop: bool = False) -> None:
    """One full fill: all quotes, then all news, then all profiles."""
    if not should_fetch_live():
        return
    if tickers is None:
        tickers = _active_tickers()
    for phase in PHASES:
        for ticker in tickers:
            if not should_fetch_live():
                return
            if respect_stop and _stop.is_set():
                return
            _refresh_phase(ticker, phase)


def refresh_ticker(ticker: str) -> None:
    """Refresh one ticker. Prefer refresh_passes so quotes are not stuck behind news."""
    refresh_passes([ticker.strip().upper()])


def _refresh_phase(ticker: str, phase: str) -> None:
    ticker = ticker.strip().upper()
    try:
        with _refresh_lock:
            client = get_client()
            if phase == "quote":
                quote = client.get_quote(ticker)
                payload = quote if isinstance(quote, dict) else {}
                price, pct = _price_from_quote(payload)
                _store_quote(ticker, price, pct, _quote_at(payload))
            elif phase == "news":
                today = date.today()
                news_from = (today - timedelta(days=30)).isoformat()
                articles = client.get_company_news(ticker, news_from, today.isoformat())
                if not isinstance(articles, list):
                    return
                picked = select_company_news(articles, ticker)
                _store_news(ticker, picked)
            elif phase == "profile":
                profile = client.get_profile(ticker)
                logo = profile.get("logo") if isinstance(profile, dict) else None
                if isinstance(logo, str) and logo.strip():
                    _store_logo(ticker, logo.strip())
    except Exception:
        logger.exception("Finnhub %s refresh failed for %s", phase, ticker)


def _quote_at(quote: dict) -> datetime | None:
    """Finnhub quote `t` is unix seconds. Missing, zero, or negative is unusable."""
    raw = quote.get("t")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if not math.isfinite(raw) or raw <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _store_quote(
    ticker: str,
    price: float | None,
    pct: float | None,
    quote_at: datetime | None,
) -> None:
    # Price, change, and timestamp are one quote. A missing timestamp is as
    # unusable as c == 0: leave the last valid cache row alone.
    if price is None or quote_at is None:
        return
    if pct is not None and (isinstance(pct, bool) or not isinstance(pct, (int, float)) or not math.isfinite(pct)):
        return

    def apply(company: Company) -> bool:
        company.current_price = float(price)
        company.price_change_percent = float(pct) if pct is not None else None
        company.latest_quote_at = quote_at
        return True

    _update_company(ticker, apply)


def _store_news(ticker: str, picked) -> None:
    def apply(company: Company) -> bool:
        if picked is None:
            company.latest_news_headline = NO_RECENT_NEWS_SENTINEL
            company.latest_news_summary = None
            company.latest_news_date = None
            company.latest_news_source = None
            company.latest_news_url = None
            return True
        company.latest_news_headline = picked.headline
        company.latest_news_summary = picked.summary
        company.latest_news_date = picked.news_date
        company.latest_news_source = picked.source
        company.latest_news_url = picked.url
        return True

    _update_company(ticker, apply)


def _store_logo(ticker: str, logo: str) -> None:
    def apply(company: Company) -> bool:
        company.logo_url = logo
        return True

    _update_company(ticker, apply)


def _update_company(ticker: str, apply) -> None:
    if dbmod.SessionLocal is None:
        return
    session = dbmod.SessionLocal()
    try:
        company = session.get(Company, ticker)
        if company is None or company.status != "active":
            return
        if apply(company):
            company.data_updated_at = utcnow()
            session.commit()
    except Exception:
        logger.exception("Could not store Finnhub fields for %s", ticker)
        session.rollback()
    finally:
        session.close()


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
        try:
            refresh_passes(respect_stop=True)
        except Exception:
            logger.exception("Finnhub refresh loop failed")
        # Quotes expire after ~5 minutes. A warm disk cache makes the next
        # pass skip network calls that are still fresh.
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
