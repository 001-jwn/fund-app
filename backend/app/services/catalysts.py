"""Catalyst alerts from cached quotes, earnings dates, and selected headlines.

Detection never calls Finnhub. The first valid observation for a user, ticker,
and kind only records a baseline. A later new key emits once. Seen does not
delete that key, so the same event cannot be emitted again.
"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Alert, AlertBaseline, Company, EarningsCalendar, Match
from app.services.cards import liked_display_name
from app.services.news import NO_RECENT_NEWS_MESSAGE, NO_RECENT_NEWS_SENTINEL

logger = logging.getLogger("fund.catalysts")

NEW_YORK = ZoneInfo("America/New_York")
SKEW = timedelta(minutes=5)
NEWS_MAX_AGE = timedelta(hours=24)
NONE_KEY = "none"

# Provisional copy. Content Writer replaces this dict later (I3).
LINE_TEMPLATES = {
    "price": "{name} moved {direction} {pct:.1f}% on {when} (last price US${price:.2f}).",
    "earnings": "{name} is scheduled to report earnings {when}{hour}.",
    "news": "News about {name}: {headline}",
}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_TERMS = (
    "earnings",
    "results",
    "acquires",
    "acquisition",
    "merger",
    "guidance",
    "outlook",
    "appoints",
    "appointed",
    "steps down",
    "resigns",
    "CEO",
    "CFO",
)
_TERM_PATTERNS = tuple(
    re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE) for term in _TERMS
)


def headline_has_catalyst_term(headline: str) -> bool:
    """True when the headline contains one of the 13 exact terms."""
    if not isinstance(headline, str) or not headline.strip():
        return False
    return any(pattern.search(headline) for pattern in _TERM_PATTERNS)


def detect_for_user(session: Session, user_id: str, now: datetime | None = None) -> None:
    """Evaluate every liked ticker. Does not call Finnhub."""
    moment = _as_utc(now)
    today_et = moment.astimezone(NEW_YORK).date()
    tomorrow_et = today_et + timedelta(days=1)
    tickers = [
        row[0]
        for row in session.query(Match.ticker).filter(Match.user_id == user_id).all()
    ]
    for ticker in tickers:
        company = session.get(Company, ticker)
        if company is None:
            continue
        _consider_price(session, user_id, company, moment, today_et)
        _consider_earnings(session, user_id, company, today_et, tomorrow_et)
        _consider_news(session, user_id, company, moment)


def detect_for_liked_users(session: Session, now: datetime | None = None) -> None:
    user_ids = [row[0] for row in session.query(Match.user_id).distinct().all()]
    for user_id in user_ids:
        detect_for_user(session, user_id, now)


def _consider_price(session: Session, user_id: str, company: Company, now: datetime, today_et) -> None:
    observed = _valid_quote(company, now)
    if observed is None:
        return
    _price, pct, quote_date = observed
    direction = "up" if pct > 0 else "down" if pct < 0 else None
    meets = direction is not None and abs(pct) >= 5.0
    key = f"{quote_date.isoformat()}|{direction}" if meets else None
    if not _past_baseline(session, user_id, company.ticker, "price", key):
        return
    assert key is not None and direction is not None
    when = f"{_MONTHS[quote_date.month - 1]} {quote_date.day}"
    facts = {
        "dp": pct,
        "c": company.current_price,
        "quote_date_et": quote_date.isoformat(),
        "direction": direction,
    }
    line = LINE_TEMPLATES["price"].format(
        name=_name(company),
        direction=direction,
        pct=abs(pct),
        when=when,
        price=float(company.current_price),
    )
    _emit(session, user_id, company.ticker, "price", key, facts, line)


def _consider_earnings(
    session: Session,
    user_id: str,
    company: Company,
    today_et,
    tomorrow_et,
) -> None:
    row = session.get(EarningsCalendar, company.ticker)
    if row is None:
        return
    report = _parse_date(row.report_date)
    in_window = report in {today_et, tomorrow_et}
    key = report.isoformat() if in_window and report is not None else None
    if not _past_baseline(session, user_id, company.ticker, "earnings", key):
        return
    assert report is not None
    when = "today" if report == today_et else "tomorrow"
    hour = _hour_clause(row.hour)
    facts = {"date": report.isoformat()}
    if row.hour:
        facts["hour"] = row.hour
    line = LINE_TEMPLATES["earnings"].format(name=_name(company), when=when, hour=hour)
    _emit(session, user_id, company.ticker, "earnings", key or report.isoformat(), facts, line)


def _consider_news(session: Session, user_id: str, company: Company, now: datetime) -> None:
    headline = _real_headline(company.latest_news_headline)
    published = _published_at(company.latest_news_unix)
    if headline is None or published is None:
        return
    if published > now + SKEW:
        return
    age = now - published
    passes_age = timedelta(0) <= age <= NEWS_MAX_AGE
    passes_term = headline_has_catalyst_term(headline)
    fingerprint = _fingerprint(company, headline)
    key = fingerprint if passes_age and passes_term else None
    if not _past_baseline(session, user_id, company.ticker, "news", key):
        return
    facts = {
        "headline": headline,
        "source": company.latest_news_source,
        "date": company.latest_news_date,
        "url": (company.latest_news_url or "").strip() or None,
    }
    line = LINE_TEMPLATES["news"].format(name=_name(company), headline=headline)
    _emit(session, user_id, company.ticker, "news", fingerprint, facts, line)


def _past_baseline(session: Session, user_id: str, ticker: str, kind: str, key: str | None) -> bool:
    """Return True only when this key should be emitted.

    The first valid observation records the key, or 'none' when the rule is
    not met, and emits nothing.
    """
    baseline = session.get(AlertBaseline, (user_id, ticker, kind))
    if baseline is None:
        session.add(
            AlertBaseline(
                user_id=user_id,
                ticker=ticker,
                kind=kind,
                baseline_key=key or NONE_KEY,
                set_at=utcnow(),
            )
        )
        return False
    if key is None or key == baseline.baseline_key:
        return False
    return True


def _emit(
    session: Session,
    user_id: str,
    ticker: str,
    kind: str,
    dedupe_key: str,
    facts: dict,
    line: str,
) -> None:
    exists = (
        session.query(Alert.id)
        .filter(
            Alert.user_id == user_id,
            Alert.ticker == ticker,
            Alert.kind == kind,
            Alert.dedupe_key == dedupe_key,
        )
        .first()
    )
    if exists is not None:
        return
    try:
        with session.begin_nested():
            session.add(
                Alert(
                    user_id=user_id,
                    ticker=ticker,
                    kind=kind,
                    dedupe_key=dedupe_key,
                    facts=json.dumps(facts, separators=(",", ":")),
                    line=line,
                    created_at=utcnow(),
                    seen=False,
                )
            )
            session.flush()
    except IntegrityError:
        logger.info("Alert already stored for %s %s %s", user_id, ticker, dedupe_key)


def _valid_quote(company: Company, now: datetime) -> tuple[float, float, object] | None:
    price = company.current_price
    pct = company.price_change_percent
    quote_at = company.latest_quote_at
    if not _finite(price) or price <= 0 or not _finite(pct):
        return None
    if not isinstance(quote_at, datetime):
        return None
    try:
        if quote_at.tzinfo is None:
            aware = quote_at.replace(tzinfo=timezone.utc)
        else:
            aware = quote_at.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None
    if aware > now + SKEW:
        return None
    quote_date = aware.astimezone(NEW_YORK).date()
    return float(price), float(pct), quote_date


def _published_at(value: float | None) -> datetime | None:
    if not _finite(value) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _fingerprint(company: Company, headline: str) -> str:
    article_id = (company.latest_news_id or "").strip()
    if article_id:
        return "id:" + article_id
    url = (company.latest_news_url or "").strip()
    return f"{company.latest_news_unix}|{headline}|{url}"


def _real_headline(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped or stripped in {NO_RECENT_NEWS_SENTINEL, NO_RECENT_NEWS_MESSAGE}:
        return None
    return value


def _hour_clause(hour: str | None) -> str:
    token = (hour or "").strip().lower()
    if token == "bmo":
        return " (before market open)"
    if token == "amc":
        return " (after market close)"
    return ""


def _parse_date(value: str | None):
    if not isinstance(value, str):
        return None
    text = value.strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _name(company: Company) -> str:
    return (liked_display_name(company) or "").strip() or company.ticker


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _as_utc(now: datetime | None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
