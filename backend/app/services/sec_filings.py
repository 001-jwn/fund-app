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
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from app import db as dbmod
from app.db import utcnow
from app.models import Company, Like, SecFetchState, SecFiling
from app.services.cards import liked_display_name
from app.services.sec_text import (
    build_summary,
    decide_filing,
    ny_dates,
    plain_text,
    same_line_within_window,
    text_is_unreadable,
)

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
DOCUMENT_TTL = timedelta(days=7)
BACKOFF_TTL = timedelta(minutes=15)
MIN_INTERVAL_SECONDS = 1.0
MAX_DOCUMENT_BYTES = 2_000_000
FILING_CAP = 10

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
    """Fetch recent 8-K metadata, then read candidate filing text.

    Safe to call by hand. A missing User-Agent or an active backoff skips the
    network. HTTP 403 or 429 stops the run and does not retry. The database
    session is not held open across the throttle wait or the network call.
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
    finally:
        session.close()
    if not tickers:
        return
    try:
        cik_by_ticker = _cik_map(user_agent)
    except SecBlocked as blocked:
        _record_backoff(blocked.status)
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
            payload = _submissions(cik, user_agent)
        except SecBlocked as blocked:
            _record_backoff(blocked.status)
            return
        except Exception:
            logger.exception("SEC submissions failed for %s. Keeping prior rows.", ticker)
            continue
        session = dbmod.SessionLocal()
        try:
            _store_filings(session, ticker, cik, payload)
            session.commit()
        finally:
            session.close()
    _confirm_pending(user_agent)


def filings_for_user(session, user_id: str) -> list[dict]:
    """Verified filings for this user's likes. No network. At most 10."""
    liked = {
        str(row[0]).strip().upper()
        for row in session.query(Like.ticker).filter(Like.user_id == user_id).all()
        if row[0]
    }
    liked -= SKIP_8K_TICKERS
    if not liked:
        return []
    rows = (
        session.query(SecFiling)
        .filter(
            SecFiling.ticker.in_(sorted(liked)),
            SecFiling.verified.is_(True),
            SecFiling.h3_category.is_not(None),
        )
        .all()
    )
    rows = [row for row in rows if (row.summary_plain or "").strip()]
    rows.sort(key=lambda row: (_accepted_sort(row.accepted_at), row.accession), reverse=True)
    kept = []
    for row in rows:
        line = (row.summary_plain or "").strip()
        if any(
            earlier.ticker == row.ticker
            and (earlier.summary_plain or "").strip() == line
            and same_line_within_window(earlier.accepted_at, row.accepted_at)
            for earlier in kept
        ):
            continue
        company = session.get(Company, row.ticker)
        dated = ny_dates(row.accepted_at)
        if company is None or dated is None:
            continue
        kept.append(row)
        if len(kept) >= FILING_CAP:
            break
    visible = []
    for row in kept:
        company = session.get(Company, row.ticker)
        dated = ny_dates(row.accepted_at)
        visible.append(
            {
                "ticker": row.ticker,
                "short_name": liked_display_name(company),
                "accession": row.accession,
                "date_ny": dated[0],
                "line": (row.summary_plain or "").strip(),
                "filing_url": row.filing_url,
            }
        )
    return visible


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


def _record_backoff(status: int) -> None:
    when = utcnow() + BACKOFF_TTL
    note = f"HTTP {status}"
    session = dbmod.SessionLocal()
    try:
        row = session.get(SecFetchState, BACKOFF_KEY)
        if row is None:
            session.add(SecFetchState(state_key=BACKOFF_KEY, backoff_until=when, note=note))
        else:
            row.backoff_until = when
            row.note = note
        session.commit()
    finally:
        session.close()
    logger.warning(
        "SEC EDGAR returned %s. Stopping this 8-K refresh and backing off.",
        note,
    )


def _cik_map(user_agent: str) -> dict[str, str]:
    payload = _cached_json("cik_map", CACHE_DIR / "company_tickers.json", CIK_MAP_TTL, CIK_MAP_URL, user_agent)
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


def _submissions(cik: str, user_agent: str) -> dict:
    url = SUBMISSIONS_URL.format(cik=cik)
    path = CACHE_DIR / "submissions" / f"{cik}.json"
    payload = _cached_json(f"submissions:{cik}", path, SUBMISSIONS_TTL, url, user_agent)
    return payload if isinstance(payload, dict) else {}


def _cached_json(key: str, path: Path, ttl: timedelta, url: str, user_agent: str):
    cached = _read_cache(path, ttl)
    if cached is not None:
        return cached
    payload = _get_json(url, user_agent)
    _write_cache(path, payload)
    _mark_fetched(key)
    return payload


def _mark_fetched(key: str) -> None:
    session = dbmod.SessionLocal()
    try:
        row = session.get(SecFetchState, key)
        if row is None:
            session.add(SecFetchState(state_key=key, fetched_at=utcnow()))
        else:
            row.fetched_at = utcnow()
        session.commit()
    finally:
        session.close()


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
    # Never faster than 10 requests per second, and never a second attempt.
    _throttle()
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
        created = row is None
        if created:
            row = SecFiling(accession=accession, ticker=ticker, cik=cik, form=form)
            session.add(row)
            pending[accession] = row
            row.h3_category = None
            row.summary_plain = None
            row.verified = False
            row.amends_accession = None
            row.text_outcome = None
        row.ticker = ticker
        row.cik = cik
        row.form = form
        row.filed_at = _text(_at(recent, "filingDate", index))
        row.accepted_at = _text(_at(recent, "acceptanceDateTime", index))
        row.items = items_text
        row.h3_candidate = h3_candidate_for_items(parse_items(items_text))
        row.filing_url = filing_url
        row.report_url = report_url


def _confirm_pending(user_agent: str) -> None:
    session = dbmod.SessionLocal()
    try:
        if _backoff_active(session):
            return
        rows = (
            session.query(SecFiling)
            .filter(SecFiling.h3_candidate.is_(True), SecFiling.text_outcome.is_(None))
            .all()
        )
        pending = [
            {
                "accession": row.accession,
                "ticker": row.ticker,
                "cik": row.cik,
                "form": row.form,
                "items": row.items,
                "report_url": row.report_url,
                "filing_url": row.filing_url,
                "accepted_at": row.accepted_at,
            }
            for row in rows
            if row.ticker not in SKIP_8K_TICKERS and row.form in KEPT_FORMS
        ]
    finally:
        session.close()
    for item in pending:
        session = dbmod.SessionLocal()
        try:
            blocked = _backoff_active(session)
        finally:
            session.close()
        if blocked:
            return
        try:
            documents = _documents_for(item, user_agent)
        except SecBlocked as blocked_error:
            _record_backoff(blocked_error.status)
            return
        except Exception:
            logger.warning("SEC document fetch failed for %s. Keeping prior rows.", item["accession"])
            continue
        decision = decide_filing(
            ticker=item["ticker"],
            form=item["form"],
            items=parse_items(item["items"]),
            accession=item["accession"],
            documents=documents,
        )
        session = dbmod.SessionLocal()
        try:
            row = session.get(SecFiling, item["accession"])
            company = session.get(Company, item["ticker"]) if row is not None else None
            if row is None or company is None:
                continue
            _apply_decision(row, decision, liked_display_name(company))
            session.commit()
        finally:
            session.close()


def _apply_decision(row: SecFiling, decision: dict, name: str) -> None:
    category = decision.get("h3_category")
    leaders = decision.get("leaders_json")
    fields = dict(decision)
    if isinstance(leaders, list):
        fields["leaders_json"] = leaders
    line = None
    if decision.get("text_outcome") == "confirmed" and category:
        line = build_summary(
            category=category,
            form=row.form,
            accepted_at=row.accepted_at,
            name=name,
            fields=fields,
        )
        if line is None:
            category = None
            decision = {**decision, "text_outcome": "unconfirmable", "verified": False, "h3_category": None}
    row.text_outcome = decision.get("text_outcome")
    row.verified = bool(decision.get("verified")) and bool(line)
    row.h3_category = category if line else None
    row.summary_plain = line
    if decision.get("amends_accession"):
        row.amends_accession = decision.get("amends_accession")
    row.measure = decision.get("measure") if line else None
    row.figure = decision.get("figure") if line else None
    row.exhibit_url = decision.get("exhibit_url") if line else None
    row.is_quarter = decision.get("is_quarter") if line else None
    row.counterparty = decision.get("counterparty") if line else None
    row.side = decision.get("side") if line else None
    row.stage = decision.get("stage") if line else None
    row.asset = decision.get("asset") if line else None
    row.person = decision.get("person") if line else None
    row.role = decision.get("role") if line else None
    row.lead_direction = decision.get("lead_direction") if line else None
    row.resigned_or_retired = decision.get("resigned_or_retired") if line else None
    row.eff_date = decision.get("eff_date") if line else None
    row.guide_direction = decision.get("guide_direction") if line else None
    row.period_label = decision.get("period_label") if line else None
    if line and isinstance(leaders, list):
        row.leaders_json = json.dumps(leaders)
    else:
        row.leaders_json = None


def _documents_for(item: dict, user_agent: str) -> list[dict]:
    cached = _read_cache(CACHE_DIR / "documents" / f"{item['accession']}.json", DOCUMENT_TTL)
    if isinstance(cached, list):
        return cached
    documents = _fetch_documents(item, user_agent)
    _write_cache(CACHE_DIR / "documents" / f"{item['accession']}.json", documents)
    return documents


def _fetch_documents(item: dict, user_agent: str) -> list[dict]:
    report_url = item.get("report_url")
    if not report_url:
        return []
    documents = [_fetch_one(report_url, user_agent, role="main", exhibit=None)]
    html = ""
    if documents[0].get("raw") and not documents[0].get("too_long"):
        html = documents[0]["raw"]
    chosen = _pick_exhibits(_find_exhibits(html, report_url))
    if not any(exhibit == "99.1" for exhibit, _url in chosen) and _mentions_exhibit_991(documents[0].get("text") or ""):
        index_url = item.get("filing_url")
        if index_url and len(documents) < 3:
            index_doc = _fetch_one(index_url, user_agent, role="index", exhibit=None)
            chosen = _pick_exhibits(_find_exhibits(index_doc.get("raw") or "", index_url))
    for exhibit, url in chosen:
        if len([doc for doc in documents if doc.get("role") != "index"]) >= 3:
            break
        documents.append(_fetch_one(url, user_agent, role="exhibit", exhibit=exhibit))
    return [doc for doc in documents if doc.get("role") != "index"]


def _fetch_one(url: str, user_agent: str, role: str, exhibit: str | None) -> dict:
    raw, size, too_long = _get_bytes(url, user_agent)
    logger.info("SEC document bytes=%s", size)
    if too_long:
        return {"url": url, "role": role, "exhibit": exhibit, "byte_size": size, "too_long": True, "text": "", "raw": ""}
    text = plain_text(raw)
    if text_is_unreadable(text):
        text = ""
    return {
        "url": url,
        "role": role,
        "exhibit": exhibit,
        "byte_size": size,
        "too_long": False,
        "text": text,
        "raw": raw,
    }


def _find_exhibits(html: str, base_url: str) -> list[tuple[str, str]]:
    found = []
    for match in _exhibit_anchors(html):
        href, label = match
        exhibit = _exhibit_number(label, href)
        if exhibit is None:
            continue
        url = urllib.parse.urljoin(base_url, href)
        if not _archive_url(url):
            continue
        found.append((exhibit, url))
    return found


def _exhibit_anchors(html: str):
    import re

    for match in re.finditer(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html or ""):
        label = re.sub(r"(?is)<[^>]+>", " ", match.group(2))
        yield match.group(1), label


def _exhibit_number(label: str, href: str) -> str | None:
    import re

    blob = f"{label} {href}"
    match = re.search(r"(?:exhibit|ex)[\s._-]*(\d{1,3})[.\-_](\d{1,3})", blob, re.I)
    if match is None:
        return None
    return f"{int(match.group(1))}.{int(match.group(2))}"


def _pick_exhibits(found: list[tuple[str, str]]) -> list[tuple[str, str]]:
    ordered = [item for item in found if item[0] == "99.1"] + [item for item in found if item[0] != "99.1"]
    picked = []
    seen = set()
    for exhibit, url in ordered:
        if url in seen:
            continue
        seen.add(url)
        picked.append((exhibit, url))
        if len(picked) == 2:
            break
    return picked


def _mentions_exhibit_991(text: str) -> bool:
    import re

    return re.search(r"exhibit\s*99\s*[\.\-_]?\s*1", text or "", re.I) is not None


def _archive_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return host.endswith("sec.gov") and "/Archives/" in parsed.path


def _get_bytes(url: str, user_agent: str) -> tuple[str, int, bool]:
    """Return raw text, byte size, and whether the body was too long to read."""
    _throttle()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            header = _content_length(response)
            if header is not None and header > MAX_DOCUMENT_BYTES:
                return "", header, True
            chunks = []
            total = 0
            while total <= MAX_DOCUMENT_BYTES:
                chunk = _read_chunk(response)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOCUMENT_BYTES:
                    return "", total, True
                chunks.append(chunk)
                if len(chunk) > 65536:
                    break
    except urllib.error.HTTPError as err:
        if err.code in {403, 429}:
            raise SecBlocked(err.code) from err
        if err.code == 404:
            return "", 0, False
        raise
    raw = b"".join(chunks)
    return raw.decode("utf-8", errors="replace"), len(raw), False


def _content_length(response) -> int | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get("Content-Length") if hasattr(headers, "get") else None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_chunk(response) -> bytes:
    try:
        return response.read(65536)
    except TypeError:
        return response.read()


def _throttle() -> None:
    global _last_request_at
    interval = max(MIN_INTERVAL_SECONDS, 0.1)
    wait = interval - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(min(wait, interval))
    _last_request_at = time.monotonic()


def _accepted_sort(value: str | None) -> str:
    return value or ""


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
