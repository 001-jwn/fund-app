"""Build the public card. holder_count is never included."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from app.interests import ALLOWED_INTERESTS
from app.models import Company, CompanyInterest, UserInterest
from app.services.news import (
    NO_RECENT_NEWS_MESSAGE,
    NO_RECENT_NEWS_SENTINEL,
    format_news_date_label,
    format_quarter_label,
)


def choose_interest_link(
    links: list[CompanyInterest],
    user_interests: set[str],
) -> CompanyInterest | None:
    """Pick the why-line for one interest the user actually picked.

    If several of the user's interests match, use the app's fixed order
    (gaming, travel, music, automobile). The line is that row's why_line
    only — lines are never combined.
    """
    matching = [link for link in links if link.interest in user_interests]
    if not matching:
        return None
    order = {name: index for index, name in enumerate(ALLOWED_INTERESTS)}
    matching.sort(key=lambda link: order.get(link.interest, 99))
    return matching[0]


def user_interest_set(rows: list[UserInterest]) -> set[str]:
    return {row.interest for row in rows}


def public_card(company: Company, link: CompanyInterest) -> dict:
    price_ok = company.current_price is not None
    raw_headline = (company.latest_news_headline or "").strip()
    if raw_headline == NO_RECENT_NEWS_SENTINEL:
        news_status = "none"
        news_message = NO_RECENT_NEWS_MESSAGE
        headline = None
        summary = None
        news_date = None
        news_ok = False
    elif raw_headline:
        news_status = "ready"
        news_message = None
        headline = company.latest_news_headline
        summary = (company.latest_news_summary or "").strip() or None
        news_date = company.latest_news_date
        news_ok = True
    else:
        news_status = "unavailable"
        news_message = None
        headline = None
        summary = None
        news_date = None
        news_ok = False
    return {
        "ticker": company.ticker,
        "company_name": company.company_name,
        "short_description": company.short_description,
        "current_price": company.current_price if price_ok else None,
        "price_change_percent": company.price_change_percent if price_ok else None,
        "price_available": price_ok,
        "latest_news_headline": headline,
        "latest_news_summary": summary,
        "latest_news_date": news_date if news_ok else None,
        "news_date_label": format_news_date_label(news_date) if news_ok else None,
        "news_available": news_ok,
        "news_status": news_status,
        "news_message": news_message,
        "quarterly_summary": company.quarterly_summary,
        "last_quarter_date": company.last_quarter_date,
        "quarter_label": format_quarter_label(company.last_quarter_date),
        "why_line": link.why_line,
        "interest": link.interest,
        "logo_url": company.logo_url or None,
    }


class LikedCompany(NamedTuple):
    ticker: str
    company_name: str
    created_at: datetime | None
    tags: frozenset[str]


def index_company_interests(
    rows: list[CompanyInterest],
) -> tuple[dict[str, list[CompanyInterest]], dict[str, set[str]]]:
    """Group every CompanyInterest row once: links for the why-line, tags for the score."""
    links_by_ticker: dict[str, list[CompanyInterest]] = {}
    tags_by_ticker: dict[str, set[str]] = {}
    for row in rows:
        links_by_ticker.setdefault(row.ticker, []).append(row)
        tags_by_ticker.setdefault(row.ticker, set()).add(row.interest)
    return links_by_ticker, tags_by_ticker


def feed_score(tags: set[str], liked: list[LikedCompany]) -> int:
    """Add up, for each liked company, how many interest tags the two companies share.

    Every tag counts, including tags the user did not pick.
    """
    return sum(len(tags & like.tags) for like in liked)


def because_liked_name(
    tags: set[str],
    card_interest: str,
    liked: list[LikedCompany],
) -> str | None:
    """Company name of the liked stock that shares the most tags besides card_interest.

    card_interest is the interest this card is shown for (choose_interest_link).
    A higher count of those other tags wins. A tie uses the later Like.created_at,
    then ticker A to Z. None when no liked company shares any other tag, including
    when the only tag in common is the one this card is being shown for.
    """
    winner: LikedCompany | None = None
    winner_count = 0
    for like in liked:
        other_count = len((tags & like.tags) - {card_interest})
        if other_count == 0:
            continue
        if winner is None or _preferred_because(like, other_count, winner, winner_count):
            winner = like
            winner_count = other_count
    if winner is None:
        return None
    return winner.company_name


def _preferred_because(
    challenger: LikedCompany,
    challenger_count: int,
    winner: LikedCompany,
    winner_count: int,
) -> bool:
    if challenger_count != winner_count:
        return challenger_count > winner_count
    challenger_at = challenger.created_at
    winner_at = winner.created_at
    if challenger_at != winner_at:
        if challenger_at is None:
            return False
        if winner_at is None:
            return True
        return challenger_at > winner_at
    return challenger.ticker < winner.ticker


def order_feed_cards(
    companies: list[Company],
    links_by_ticker: dict[str, list[CompanyInterest]],
    tags_by_ticker: dict[str, set[str]],
    user_interests: set[str],
    liked: list[LikedCompany],
) -> list[dict]:
    """Cards that match a picked interest, highest score first, then ticker A to Z."""
    scored: list[tuple[int, str, dict]] = []
    for company in companies:
        links = links_by_ticker.get(company.ticker, [])
        link = choose_interest_link(links, user_interests)
        if link is None:
            continue
        tags = tags_by_ticker.get(company.ticker, set())
        card = public_card(company, link)
        card["because_liked"] = because_liked_name(tags, link.interest, liked)
        scored.append((feed_score(tags, liked), company.ticker, card))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]
