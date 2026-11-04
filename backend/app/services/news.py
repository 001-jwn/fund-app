"""Pick a company-news item and format the card's date lines.

Rules live in backend/app/seed/news_match_rules.json. An article counts only
when the headline or summary contains one of that ticker's aliases as a whole
word. Tickers in no_bare_ticker never match as a bare word; $TICKER and
(TICKER) still count. Finnhub's `related` field is not trusted: roundups are
tagged with many tickers, so the name check always runs. The most recent
matching article wins. There is no ranking score.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Stored on the company row when a news fetch succeeded and nothing matched.
# It is not a headline. The card turns it into NO_RECENT_NEWS_MESSAGE.
NO_RECENT_NEWS_SENTINEL = "__no_recent_company_news__"
NO_RECENT_NEWS_MESSAGE = "No recent news about this company yet."

RULES_PATH = Path(__file__).resolve().parents[1] / "seed" / "news_match_rules.json"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MIN_SUMMARY_CHARS = 20

_rules_cache: dict | None = None
_boilerplate_cache: list[re.Pattern[str]] | None = None


@dataclass(frozen=True)
class SelectedNews:
    headline: str
    summary: str | None
    news_date: str | None


def load_rules() -> dict:
    global _rules_cache, _boilerplate_cache
    if _rules_cache is None:
        _rules_cache = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        _boilerplate_cache = [
            re.compile(pattern, re.DOTALL) for pattern in _rules_cache.get("summary_boilerplate_patterns") or []
        ]
    return _rules_cache


def clean_summary(summary: str | None, headline: str | None = None) -> str | None:
    """Strip boilerplate, then hide empty, tiny, or headline-copy summaries."""
    if not isinstance(summary, str):
        return None
    load_rules()
    text = summary
    for pattern in _boilerplate_cache or []:
        text = pattern.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) < _MIN_SUMMARY_CHARS:
        return None
    if headline and _same_text(text, headline):
        return None
    return text


def select_company_news(articles: list, ticker: str) -> SelectedNews | None:
    """Most recent article whose headline or summary matches this ticker's aliases.

    `related` is ignored as proof. A roundup can list the ticker and still be dropped.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None
    candidates: list[tuple[float, dict]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        headline = article.get("headline")
        if not isinstance(headline, str) or not headline.strip():
            continue
        summary = article.get("summary") if isinstance(article.get("summary"), str) else ""
        if not _text_matches_ticker(f"{headline}\n{summary}", ticker):
            continue
        when = article.get("datetime")
        stamp = float(when) if isinstance(when, (int, float)) and not isinstance(when, bool) else 0.0
        candidates.append((stamp, article))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _stamp, newest = candidates[0]
    headline = str(newest.get("headline")).strip()
    raw_summary = newest.get("summary") if isinstance(newest.get("summary"), str) else None
    summary = clean_summary(raw_summary, headline)
    return SelectedNews(headline=headline, summary=summary, news_date=_iso_from_unix(newest.get("datetime")))


def _text_matches_ticker(text: str, ticker: str) -> bool:
    rules = load_rules()
    bare_blocked = ticker in set(rules.get("no_bare_ticker") or [])
    if bare_blocked and _decorated_ticker(text, ticker):
        return True
    for alias in (rules.get("aliases") or {}).get(ticker) or []:
        cleaned = alias.strip()
        if not cleaned:
            continue
        # The alias list sometimes repeats the ticker. For no_bare_ticker symbols
        # that repeat is not a bare-word match; only $TICKER and (TICKER) count.
        if cleaned.upper() == ticker and bare_blocked:
            continue
        if _whole_word(text, cleaned):
            return True
    return False


def _whole_word(text: str, phrase: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _decorated_ticker(text: str, ticker: str) -> bool:
    """$TICKER or (TICKER). Not a bare ticker and not U.S. / U.K."""
    token = re.escape(ticker)
    return re.search(rf"(?:\${token}(?!\w)|\({token}\))", text, flags=re.IGNORECASE) is not None


def _same_text(left: str, right: str) -> bool:
    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold().rstrip(".")

    return norm(left) == norm(right)


def format_news_date_label(iso_date: str | None) -> str | None:
    parsed = _parse_iso_date(iso_date)
    if parsed is None:
        return None
    return f"News from {_MONTHS[parsed.month - 1]} {parsed.day}"


def format_quarter_label(iso_date: str | None) -> str | None:
    parsed = _parse_iso_date(iso_date)
    if parsed is None:
        return None
    return f"Last quarter (ended {_MONTHS[parsed.month - 1]} {parsed.day}, {parsed.year})"


def _iso_from_unix(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return time.strftime("%Y-%m-%d", time.gmtime(value))


def _parse_iso_date(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) >= 10:
        text = text[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
