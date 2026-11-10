"""Cache SEC 8-K metadata for liked US filers. No summaries and no UI.

John's decision: strict 8-K only. NTES, SONY, SPOT, TM, and RACE are skipped.
This module does not read 6-K or 20-F and does not relabel those forms as 8-K.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from app import db as dbmod
from app.db import utcnow
from app.models import Company, Like, SecFetchState, SecFiling

logger = logging.getLogger("fund.sec")

# John's decision: strict 8-K only. No 6-K and no 20-F handling for these filers.
SKIP_8K_TICKERS = frozenset({"NTES", "SONY", "SPOT", "TM", "RACE"})

# Soft candidate filter from item numbers only. Not a final classification.
H3_CANDIDATE_ITEMS = frozenset({"1.01", "2.01", "2.02", "5.02", "7.01", "8.01"})

KEPT_FORMS = frozenset({"8-K", "8-K/A"})

ENV_USER_AGENT = "SEC_USER_AGENT"
CIK_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
CIK_MAP_TTL = timedelta(days=30)
SUBMISSIONS_TTL = timedelta(hours=6)
BACKOFF_TTL = timedelta(minutes=15)
MIN_INTERVAL_SECONDS = 1.0

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "sec"
BACKOFF_KEY = "backoff"

_last_request_at = 0.0
_logged_missing_user_agent = False


class SecBlocked(Exception):
    def __init__(self, status: int):
        self.status = status
        super().__init__(f"HTTP {status}")


def sec_user_agent_is_set() -> bool:
    return bool(os.environ.get(ENV_USER_AGENT, "").strip())


def parse_items(raw) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def h3_candidate_for_items(items: list[str]) -> bool:
    return any(item in H3_CANDIDATE_ITEMS for item in items)


def candidate_filings_for_user(session, user_id: str) -> list[SecFiling]:
    """Liked, non-skipped tickers, and only rows flagged as soft candidates."""
    liked = {
        str(row[0]).strip().upper()
        for row in session.query(Like.ticker).filter(Like.user_id == user_id).all()
        if row[0]
    }
    liked -= SKIP_8K_TICKERS
    if not liked:
        return []
    return (
        session.query(SecFiling)
        .filter(SecFiling.ticker.in_(sorted(liked)), SecFiling.h3_candidate.is_(True))
        .order_by(SecFiling.filed_at.desc(), SecFiling.accession)
        .all()
    )


def refresh_liked_8k_filings() -> None:
    """Fetch recent 8-K metadata for tickers at least one user likes.

    Safe to call by hand. A missing User-Agent or an active backoff skips the
    network. HTTP 403 or 429 stops the run and does not retry.
    """
    global _logged_missing_user_agent
    user_agent = os.environ.get(ENV_USER_AGENT, "").strip()
    if not user_agent:
        if not _logged_missing_user_agent:
            logger.warning("SEC_USER_AGENT is not set. Skipping SEC 8-K refresh.")
            _logged_missing_user_agent = True
        return
    if dbmod.SessionLocal is None:
        logger.warning("Database is not ready. Skipping SEC 8-K refresh.")
        return
    session = dbmod.SessionLocal()
    try:
        if _backoff_active(session):
            logger.warning("SEC 8-K refresh is in backoff. Skipping this run.")
            return
        tickers = _liked_tickers(session)
        if not tickers:
            return
        try:
            cik_by_ticker = _cik_map(session, user_agent)
        except SecBlocked as blocked:
            _record_backoff(session, blocked.status)
            return
        except Exception:
            logger.exception("SEC ticker map failed. Keeping any filings already stored.")
            return
        for ticker in tickers:
            cik = cik_by_ticker.get(ticker)
            if not cik:
                logger.info("No CIK for %s. Skipping that ticker.", ticker)
                continue
            try:
                payload = _submissions(session, cik, user_agent)
            except SecBlocked as blocked:
                _record_backoff(session, blocked.status)
                return
            except Exception:
                logger.exception("SEC submissions failed for %s. Keeping prior rows.", ticker)
                continue
            _store_filings(session, ticker, cik, payload)
            session.commit()
    finally:
        session.close()


def _liked_tickers(session) -> list[str]:
    found = {
        str(row[0]).strip().upper()
        for row in session.query(Like.ticker).distinct().all()
        if row[0]
    }
    return sorted(ticker for ticker in found if ticker not in SKIP_8K_TICKERS)


def _backoff_active(session) -> bool:
    row = session.get(SecFetchState, BACKOFF_KEY)
    if row is None or row.backoff_until is None:
        return False
    return row.backoff_until > utcnow()


def _record_backoff(session, status: int) -> None:
    when = utcnow() + BACKOFF_TTL
    row = session.get(SecFetchState, BACKOFF_KEY)
    note = f"HTTP {status}"
    if row is None:
        session.add(SecFetchState(state_key=BACKOFF_KEY, backoff_until=when, note=note))
    else:
        row.backoff_until = when
        row.note = note
    session.commit()
    logger.warning(
        "SEC EDGAR returned %s. Stopping this 8-K refresh and backing off.",
        note,
    )


def _cik_map(session, user_agent: str) -> dict[str, str]:
    payload = _cached_json(session, "cik_map", CACHE_DIR / "company_tickers.json", CIK_MAP_TTL, CIK_MAP_URL, user_agent)
    mapping: dict[str, str] = {}
    values = payload.values() if isinstance(payload, dict) else payload
    if not isinstance(values, list) and isinstance(payload, dict):
        values = list(payload.values())
    if not isinstance(values, list):
        return mapping
    for item in values:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        cik = _cik_ten(item.get("cik_str"))
        if ticker and cik:
            mapping[ticker] = cik
    return mapping


def _submissions(session, cik: str, user_agent: str) -> dict:
    url = SUBMISSIONS_URL.format(cik=cik)
    path = CACHE_DIR / "submissions" / f"{cik}.json"
    payload = _cached_json(session, f"submissions:{cik}", path, SUBMISSIONS_TTL, url, user_agent)
    return payload if isinstance(payload, dict) else {}


def _cached_json(session, key: str, path: Path, ttl: timedelta, url: str, user_agent: str):
    cached = _read_cache(path, ttl)
    if cached is not None:
        return cached
    payload = _get_json(url, user_agent)
    _write_cache(path, payload)
    row = session.get(SecFetchState, key)
    if row is None:
        session.add(SecFetchState(state_key=key, fetched_at=utcnow()))
    else:
        row.fetched_at = utcnow()
    session.commit()
    return payload


def _read_cache(path: Path, ttl: timedelta):
    if not path.is_file():
        return None
    try:
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        fetched = wrapper.get("fetched_at")
        if not isinstance(fetched, str):
            return None
        stamp = datetime.fromisoformat(fetched)
        if utcnow() - stamp > ttl:
            return None
        return wrapper.get("data")
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _write_cache(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": utcnow().isoformat(), "data": data}),
        encoding="utf-8",
    )


def _get_json(url: str, user_agent: str):
    global _last_request_at
    interval = max(MIN_INTERVAL_SECONDS, 0.1)
    wait = interval - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(min(wait, interval))
    # Never faster than 10 requests per second, and never a second attempt.
    _last_request_at = time.monotonic()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as err:
        if err.code in {403, 429}:
            raise SecBlocked(err.code) from err
        raise
    return json.loads(body.decode("utf-8"))


def _store_filings(session, ticker: str, cik: str, payload: dict) -> None:
    if session.get(Company, ticker) is None:
        return
    recent = ((payload.get("filings") or {}).get("recent") or {}) if isinstance(payload, dict) else {}
    accessions = recent.get("accessionNumber") if isinstance(recent, dict) else None
    if not isinstance(accessions, list):
        return
    pending: dict[str, SecFiling] = {}
    for index, raw_accession in enumerate(accessions):
        accession = str(raw_accession or "").strip()
        if not accession:
            continue
        form = _at(recent, "form", index)
        form = form.strip() if isinstance(form, str) else ""
        if form not in KEPT_FORMS:
            continue
        raw_items = _at(recent, "items", index)
        items_text = raw_items if isinstance(raw_items, str) else None
        primary = _at(recent, "primaryDocument", index)
        primary = primary.strip() if isinstance(primary, str) and primary.strip() else None
        filing_url, report_url = _urls(cik, accession, primary)
        row = pending.get(accession) or session.get(SecFiling, accession)
        if row is None:
            row = SecFiling(accession=accession, ticker=ticker, cik=cik, form=form)
            session.add(row)
            pending[accession] = row
        row.ticker = ticker
        row.cik = cik
        row.form = form
        row.filed_at = _text(_at(recent, "filingDate", index))
        row.accepted_at = _text(_at(recent, "acceptanceDateTime", index))
        row.items = items_text
        row.h3_candidate = h3_candidate_for_items(parse_items(items_text))
        row.h3_category = None
        row.filing_url = filing_url
        row.report_url = report_url
        row.summary_plain = None
        row.verified = False
        row.amends_accession = None


def _urls(cik: str, accession: str, primary: str | None) -> tuple[str, str | None]:
    cik_int = str(int(cik))
    folder = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{folder}"
    index = f"{base}/{accession}-index.html"
    report = f"{base}/{primary}" if primary else None
    return index, report


def _at(recent: dict, name: str, index: int):
    values = recent.get(name)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _text(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _cik_ten(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    digits = str(value).strip()
    if not digits.isdigit():
        return None
    return digits.zfill(10)[-10:]
