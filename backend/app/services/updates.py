"""Build the Updates lines from cached quote and news fields. No network calls."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from app.models import Company
from app.services.cards import liked_display_name
from app.services.news import NO_RECENT_NEWS_MESSAGE, NO_RECENT_NEWS_SENTINEL

_NEW_YORK = ZoneInfo("America/New_York")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def build_update(company: Company) -> dict | None:
    """One liked company, or None when there is nothing real to say.

    A bad cached number or timestamp skips that line. It does not raise,
    so the next ticker can still be shown.
    """
    try:
        name = (liked_display_name(company) or "").strip()
    except (TypeError, ValueError):
        return None
    lines: list[str] = []
    price_line = _price_line(company, name)
    if price_line:
        lines.append(price_line)
    news_line, news_url = _news_line(company, name)
    if news_line:
        lines.append(news_line)
    else:
        news_url = None
    if not lines:
        return None
    return {"ticker": company.ticker, "lines": lines, "news_url": news_url}


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _price_line(company: Company, name: str) -> str | None:
    if not name:
        return None
    price = company.current_price
    pct = company.price_change_percent
    if not _finite_number(price) or price <= 0 or not _finite_number(pct):
        return None
    try:
        quote_date = _new_york_day(company.latest_quote_at)
        if quote_date is None:
            return None
        rounded = Decimal(str(pct)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        price_text = f"{float(price):.2f}"
    except (InvalidOperation, ValueError, OverflowError, OSError, TypeError):
        return None
    if rounded == 0:
        return f"{name} is about flat (as of {quote_date}), at US${price_text}."
    shown = f"{abs(rounded):.1f}"
    if rounded > 0:
        return f"{name} is up {shown}% (as of {quote_date}), at US${price_text}."
    return f"{name} is down {shown}% (as of {quote_date}), at US${price_text}."


def _news_line(company: Company, name: str) -> tuple[str | None, str | None]:
    headline = _real_headline(company.latest_news_headline)
    if headline is None or not name:
        return None, None
    news_date = _cached_day(company.latest_news_date)
    if news_date is None:
        return None, None
    source = (company.latest_news_source or "").strip()
    if source:
        line = f'In the news for {name}: "{headline}" ({source}, {news_date}).'
    else:
        line = f'In the news for {name}: "{headline}" ({news_date}).'
    url = (company.latest_news_url or "").strip() or None
    return line, url


def _real_headline(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped in {NO_RECENT_NEWS_SENTINEL, NO_RECENT_NEWS_MESSAGE}:
        return None
    return value


def _new_york_day(quote_at: datetime | None) -> str | None:
    """Calendar day of a naive UTC quote timestamp in America/New_York."""
    if not isinstance(quote_at, datetime):
        return None
    try:
        if quote_at.tzinfo is not None:
            aware = quote_at.astimezone(timezone.utc)
        else:
            aware = quote_at.replace(tzinfo=timezone.utc)
        local = aware.astimezone(_NEW_YORK)
    except (OverflowError, OSError, ValueError, TypeError):
        return None
    # Unix 0 is 1969-12-31 in New York. That is not a quote date.
    if local.year < 1971:
        return None
    return f"{_MONTHS[local.month - 1]} {local.day}"


def _cached_day(iso_date: str | None) -> str | None:
    if not isinstance(iso_date, str):
        return None
    text = iso_date.strip()
    if len(text) >= 10:
        text = text[:10]
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return f"{_MONTHS[parsed.month - 1]} {parsed.day}"
