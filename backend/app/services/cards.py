"""Build the public card. holder_count is never included."""

from __future__ import annotations

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
