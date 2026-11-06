"""Rolling 24-hour For-you digest. Reads the cache only. No Finnhub calls.

J2 templates, written 2026-11-05. Swap DIGEST_TEMPLATES when the wording changes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Company
from app.services.cards import liked_display_name
from app.services.catalysts import (
    NEW_YORK,
    SKEW,
    _published_at,
    _real_headline,
    _single_quotes,
    _valid_quote,
)

# Word for word from the Content Writer's J2 file, 2026-11-05.
# intro and more_line are not used: the locked shape dropped those fields.
DIGEST_TEMPLATES = {
    "header": "For you, {digest_date}",
    "price_up": "{name} is up {pct}% (as of {quote_date}), at US${price}.",
    "price_down": "{name} is down {pct}% (as of {quote_date}), at US${price}.",
    "news": 'In the news for {name}: "{headline}" ({source}, {date}).',
    "news_no_source": 'In the news for {name}: "{headline}" ({date}).',
    "news_after_price": 'In the news: "{headline}" ({source}, {date}).',
    "news_after_price_no_source": 'In the news: "{headline}" ({date}).',
    "empty": (
        "Quiet one: no price moves of 2% or more and no new headlines "
        "for your liked stocks in the last day."
    ),
}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WINDOW = timedelta(hours=24)
DIGEST_CAP = 5
_MOVE = 2.0


def build_digest(
    companies: list[Company],
    now: datetime | None = None,
    *,
    has_likes: bool,
) -> dict:
    """One item per qualifying liked stock, recomputed every request."""
    moment = _as_utc(now)
    today = moment.astimezone(NEW_YORK).date()
    ranked: list[tuple] = []
    for company in companies:
        try:
            row = _candidate(company, moment)
        except (ArithmeticError, ValueError, OverflowError, OSError, TypeError):
            continue
        if row is None:
            continue
        ranked.append(row)
    ranked.sort(key=lambda row: row[0])
    shown = ranked[:DIGEST_CAP]
    items = [
        {"ticker": row[1], "short_name": row[2], "line": row[3]}
        for row in shown
    ]
    empty_line = None
    if has_likes and not items:
        empty_line = DIGEST_TEMPLATES["empty"]
    return {
        "date": today.isoformat(),
        "header": DIGEST_TEMPLATES["header"].format(digest_date=_weekday(today)),
        "items": items,
        "empty_line": empty_line,
    }


def _candidate(company: Company, now: datetime) -> tuple | None:
    name = (liked_display_name(company) or "").strip()
    price_part, abs_dp = _price_part(company, now, name)
    news_part, news_unix = _news_part(company, now, name, with_name=price_part is None)
    if price_part and news_part:
        line = price_part + " " + news_part
    elif price_part:
        line = price_part
    elif news_part:
        line = news_part
    else:
        return None
    if price_part:
        sort_key = (0, -abs_dp, 0.0, company.ticker)
    else:
        sort_key = (1, 0.0, -news_unix, company.ticker)
    return sort_key, company.ticker, name, line


def _price_part(company: Company, now: datetime, name: str) -> tuple[str | None, float]:
    observed = _valid_quote(company, now)
    if observed is None or not name:
        return None, 0.0
    price, pct, quote_date = observed
    # Gate on the raw percent. 1.96 would display as 2.0 and must still be excluded.
    if abs(pct) < _MOVE:
        return None, 0.0
    quote_at = _aware(company.latest_quote_at)
    if quote_at is None or quote_at <= now - _WINDOW:
        return None, 0.0
    template = DIGEST_TEMPLATES["price_up" if pct > 0 else "price_down"]
    line = template.format(
        name=name,
        pct=f"{abs(pct):.1f}",
        quote_date=f"{_MONTHS[quote_date.month - 1]} {quote_date.day}",
        price=f"{price:.2f}",
    )
    return line, abs(pct)


def _news_part(
    company: Company,
    now: datetime,
    name: str,
    *,
    with_name: bool,
) -> tuple[str | None, float]:
    headline = _real_headline(company.latest_news_headline)
    published = _published_at(company.latest_news_unix)
    if headline is None or published is None or not name:
        return None, 0.0
    if published > now + SKEW or published <= now - _WINDOW:
        return None, 0.0
    local = published.astimezone(NEW_YORK)
    if local.year < 1971:
        return None, 0.0
    shown_date = f"{_MONTHS[local.month - 1]} {local.day}"
    safe = _single_quotes(headline)
    source = (company.latest_news_source or "").strip()
    if with_name:
        template = DIGEST_TEMPLATES["news"] if source else DIGEST_TEMPLATES["news_no_source"]
        line = template.format(name=name, headline=safe, source=source, date=shown_date)
    else:
        template = (
            DIGEST_TEMPLATES["news_after_price"]
            if source
            else DIGEST_TEMPLATES["news_after_price_no_source"]
        )
        line = template.format(headline=safe, source=source, date=shown_date)
    return line, published.timestamp()


def _aware(quote_at: datetime | None) -> datetime | None:
    if not isinstance(quote_at, datetime):
        return None
    try:
        if quote_at.tzinfo is None:
            return quote_at.replace(tzinfo=timezone.utc)
        return quote_at.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def _weekday(day) -> str:
    return f"{_WEEKDAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"


def _as_utc(now: datetime | None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)
