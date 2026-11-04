"""Request and response shapes for the Milestone 1 API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardingIn(BaseModel):
    interests: list[str] = Field(default_factory=list)


class OnboardingOut(BaseModel):
    user_id: str


class SwipeIn(BaseModel):
    user_id: str
    ticker: str


class SwipeOut(BaseModel):
    ok: bool
    user_id: str
    ticker: str
    matched: bool = False


class CardOut(BaseModel):
    ticker: str
    company_name: str
    short_description: str | None = None
    current_price: float | None = None
    price_change_percent: float | None = None
    price_available: bool
    latest_news_headline: str | None = None
    latest_news_summary: str | None = None
    latest_news_date: str | None = None
    news_date_label: str | None = None
    news_available: bool
    news_status: str
    news_message: str | None = None
    quarterly_summary: str | None = None
    last_quarter_date: str | None = None
    quarter_label: str | None = None
    why_line: str
    interest: str
    logo_url: str | None = None
    because_liked: str | None = None


class CardsOut(BaseModel):
    cards: list[CardOut]


class MatchOut(CardOut):
    matched_at: str


class MatchesOut(BaseModel):
    matches: list[MatchOut]


class HealthOut(BaseModel):
    status: str
    finnhub: str
