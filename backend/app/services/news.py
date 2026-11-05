"""Pick a company-news item and format the card's date lines.

Rules live in backend/app/seed/news_match_rules.json. An article counts only
when an alias appears in the HEADLINE as a whole word. Tickers in
no_bare_ticker never match as a bare word; $TICKER and (TICKER) still count.
Roundups, multi-company lists, passing-mention clickbait, advice headlines,
trailing mentions, and articles with no usable summary are rejected. A
headline that names another company is rejected too, unless that name is a
whole word inside this ticker's own aliases or company name. Finnhub's
`related` field is not trusted. The most recent surviving article wins.
There is no ranking score beyond recency.
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
COMPANIES_PATH = RULES_PATH.parent / "seed_companies.json"

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DEFAULT_MIN_SUMMARY_CHARS = 20
# A cut-off feed ending: two or more dots, or the single ellipsis character.
_TRAILING_CUTOFF = re.compile(r"(?:\s*(?:\.{2,}|…))+\s*$")

_rules_cache: dict | None = None
_boilerplate_cache: list[re.Pattern[str]] | None = None
_roundup_cache: list[re.Pattern[str]] | None = None
_passing_cache: list[re.Pattern[str]] | None = None
_question_cache: list[re.Pattern[str]] | None = None
_advice_cache: list[re.Pattern[str]] | None = None
_multi_list_cache: re.Pattern[str] | None = None
_company_name_cache: dict[str, str] | None = None


@dataclass(frozen=True)
class SelectedNews:
    headline: str
    summary: str | None
    news_date: str | None
    source: str | None = None
    url: str | None = None


def load_rules() -> dict:
    global _rules_cache, _boilerplate_cache, _roundup_cache, _passing_cache
    global _question_cache, _advice_cache, _multi_list_cache
    if _rules_cache is None:
        _rules_cache = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        _boilerplate_cache = [
            re.compile(pattern, re.DOTALL)
            for pattern in _rules_cache.get("summary_boilerplate_patterns") or []
        ]
        _roundup_cache = [
            re.compile(pattern) for pattern in _rules_cache.get("roundup_headline_patterns") or []
        ]
        _passing_cache = [
            re.compile(pattern)
            for pattern in _rules_cache.get("passing_mention_headline_patterns") or []
        ]
        _question_cache = [
            re.compile(pattern)
            for pattern in _rules_cache.get("question_clickbait_headline_patterns") or []
        ]
        _advice_cache = [
            re.compile(r"(?<!\w)" + re.escape(phrase.strip()) + r"(?!\w)", re.IGNORECASE)
            for phrase in _rules_cache.get("advice_headline_patterns") or []
            if isinstance(phrase, str) and phrase.strip()
        ]
        multi = _rules_cache.get("multi_company_list_headline_pattern")
        _multi_list_cache = re.compile(multi) if multi else None
    return _rules_cache


def _trim_trailing_ellipsis(text: str) -> str:
    """Drop a cut-off ending ('...' or '…') and the whitespace around it.

    A normal sentence period stays. Finnhub sometimes truncates the text.
    """
    return _TRAILING_CUTOFF.sub("", text.rstrip()).rstrip()


def clean_summary(summary: str | None, headline: str | None = None) -> str | None:
    """Strip boilerplate, then hide empty, tiny, or headline-copy summaries."""
    if not isinstance(summary, str):
        return None
    rules = load_rules()
    min_chars = int(rules.get("min_summary_chars") or _DEFAULT_MIN_SUMMARY_CHARS)
    text = summary
    for pattern in _boilerplate_cache or []:
        text = pattern.sub("", text)
    text = _trim_trailing_ellipsis(re.sub(r"\s+", " ", text).strip())
    if not text or len(text) < min_chars:
        return None
    compared = _trim_trailing_ellipsis(headline) if isinstance(headline, str) else None
    if compared and _same_text(text, compared):
        return None
    return text


def select_company_news(articles: list, ticker: str) -> SelectedNews | None:
    """Most recent article that passes the F1 headline-relevance rules.

    `related` is ignored as proof. A roundup can list the ticker and still be dropped.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None
    load_rules()
    candidates: list[tuple[float, dict]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        if _reject_reason(article, ticker) is not None:
            continue
        when = article.get("datetime")
        stamp = float(when) if isinstance(when, (int, float)) and not isinstance(when, bool) else 0.0
        candidates.append((stamp, article))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _stamp, newest = candidates[0]
    headline = _trim_trailing_ellipsis(str(newest.get("headline")).strip())
    raw_summary = newest.get("summary") if isinstance(newest.get("summary"), str) else None
    summary = clean_summary(raw_summary, headline)
    return SelectedNews(
        headline=headline,
        summary=summary,
        news_date=_iso_from_unix(newest.get("datetime")),
        source=_optional_text(newest.get("source")),
        url=_optional_text(newest.get("url")),
    )


def _reject_reason(article: dict, ticker: str) -> str | None:
    """Return a short reason string when the article must not be shown, else None."""
    rules = load_rules()
    headline = article.get("headline")
    if not isinstance(headline, str) or not headline.strip():
        return "no_headline"
    summary = article.get("summary") if isinstance(article.get("summary"), str) else ""

    span = _alias_span(headline, ticker)
    if span is None:
        if rules.get("require_alias_in_headline", True):
            if summary and _alias_span(summary, ticker) is not None:
                return "summary_only"
            return "no_alias_in_headline"
        # Legacy path: allow headline-or-summary (not used by F1 rules).
        if not _text_matches_ticker(f"{headline}\n{summary}", ticker):
            return "no_alias_match"

    for pattern in _roundup_cache or []:
        if pattern.search(headline):
            return "roundup"
    for pattern in _passing_cache or []:
        if pattern.search(headline):
            return "passing_mention"
    for pattern in _advice_cache or []:
        if pattern.search(headline):
            return "advice_headline"
    if _multi_list_cache is not None and _multi_list_cache.search(headline):
        return "multi_company_list"

    cleaned = clean_summary(summary, headline)
    bare = cleaned is None
    for pattern in _question_cache or []:
        if pattern.search(headline) and bare:
            return "question_clickbait_no_summary"
    if bare:
        return "no_usable_summary"

    others = _other_notable_names(headline, ticker)
    max_others = int(rules.get("max_other_notable_names_in_headline", 1))
    if len(others) > max_others:
        return "too_many_other_names"

    if span is not None:
        min_start = int(rules.get("trailing_mention_min_start", 40))
        max_frac = float(rules.get("trailing_mention_max_frac", 0.5))
        if span[0] > max(min_start, int(len(headline) * max_frac)):
            return "trailing_company_mention"

        if rules.get("reject_when_other_company_leads_headline", True) and others:
            for other in others:
                match = re.search(
                    r"(?<!\w)" + re.escape(other) + r"(?!\w)", headline, flags=re.IGNORECASE
                )
                if match and match.start() <= 1 and span[0] > match.end():
                    return "other_company_is_subject"

    return None


def _text_matches_ticker(text: str, ticker: str) -> bool:
    return _alias_span(text, ticker) is not None


def _alias_span(text: str, ticker: str) -> tuple[int, int, str] | None:
    """Earliest whole-word alias (or decorated ticker) match in text, or None."""
    rules = load_rules()
    bare_blocked = ticker in set(rules.get("no_bare_ticker") or [])
    best: tuple[int, int, str] | None = None
    for alias in (rules.get("aliases") or {}).get(ticker) or []:
        cleaned = alias.strip()
        if not cleaned:
            continue
        # The alias list sometimes repeats the ticker. For no_bare_ticker symbols
        # that repeat is not a bare-word match; only $TICKER and (TICKER) count.
        if cleaned.upper() == ticker and bare_blocked:
            continue
        match = re.search(
            r"(?<!\w)" + re.escape(cleaned) + r"(?!\w)", text, flags=re.IGNORECASE
        )
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), match.end(), cleaned)
    if bare_blocked and _decorated_ticker_span(text, ticker) is not None:
        dec = _decorated_ticker_span(text, ticker)
        assert dec is not None
        if best is None or dec[0] < best[0]:
            best = dec
    return best


def _company_name(ticker: str) -> str:
    global _company_name_cache
    if _company_name_cache is None:
        payload = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
        names: dict[str, str] = {}
        for company in payload.get("companies") or []:
            symbol = str(company.get("ticker") or "").strip().upper()
            name = company.get("company_name")
            if symbol and isinstance(name, str) and name.strip():
                names[symbol] = name.strip()
        _company_name_cache = names
    return _company_name_cache.get(ticker, "")


def _own_labels(ticker: str, rules: dict) -> list[str]:
    """Aliases plus the seed company name. The ticker itself counts too."""
    labels: list[str] = []
    for alias in (rules.get("aliases") or {}).get(ticker) or []:
        cleaned = alias.strip()
        if cleaned and cleaned not in labels:
            labels.append(cleaned)
    company = _company_name(ticker)
    if company and company not in labels:
        labels.append(company)
    if ticker and ticker not in labels:
        labels.append(ticker)
    return labels


def _part_of_own_name(name: str, labels: list[str]) -> bool:
    """True when name is a whole word inside an own alias or company name.

    Booking is on the other-names list, and it is also a word inside
    Booking Holdings, so BKNG must not treat its own name as a rival.
    """
    return any(_whole_word(label, name) for label in labels)


def _other_notable_names(headline: str, ticker: str) -> list[str]:
    rules = load_rules()
    own_labels = _own_labels(ticker, rules)
    candidates: set[str] = set(rules.get("notable_other_names") or [])
    for other_ticker, aliases in (rules.get("aliases") or {}).items():
        if other_ticker == ticker:
            continue
        for alias in aliases or []:
            cleaned = alias.strip()
            if len(cleaned) >= 3:
                candidates.add(cleaned)
    found: list[str] = []
    for name in sorted(candidates, key=len, reverse=True):
        if _part_of_own_name(name, own_labels):
            continue
        if any(name.lower() == prior.lower() for prior in found):
            continue
        if _whole_word(headline, name):
            found.append(name)
    return found


def _whole_word(text: str, phrase: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _decorated_ticker(text: str, ticker: str) -> bool:
    return _decorated_ticker_span(text, ticker) is not None


def _decorated_ticker_span(text: str, ticker: str) -> tuple[int, int, str] | None:
    """$TICKER or (TICKER). Not a bare ticker and not U.S. / U.K."""
    token = re.escape(ticker)
    match = re.search(rf"(?:\${token}(?!\w)|\({token}\))", text, flags=re.IGNORECASE)
    if match is None:
        return None
    return (match.start(), match.end(), match.group(0))


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


def _optional_text(value) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


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
