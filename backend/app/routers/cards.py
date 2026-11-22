"""Swipe cards for one user's interests."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import BAD_REQUEST, USER_NOT_FOUND
from app.models import Company, CompanyInterest, Dislike, Like, User, UserInterest
from app.schemas import API_ERROR_RESPONSES, CardOut, CardsOut
from app.services.cards import (
    LikedCompany,
    index_company_interests,
    liked_display_name,
    order_feed_cards,
)

# Digits only, with an optional leading minus. "10.0", " 10", and "+10" are not this.
_CANONICAL_LIMIT = re.compile(r"-?\d+")

router = APIRouter()

# Omitted `limit` stays 10, which is what main returns today.
DEFAULT_CARD_LIMIT = 10
MAX_CARD_LIMIT = 50


def _canonical_limit(request: Request) -> int:
    """One integer query value, or the default of 10 when limit is omitted."""
    values = request.query_params.getlist("limit")
    if not values:
        return DEFAULT_CARD_LIMIT
    if len(values) != 1 or _CANONICAL_LIMIT.fullmatch(values[0]) is None:
        raise HTTPException(status_code=422, detail=BAD_REQUEST)
    number = int(values[0])
    if number < 1 or number > MAX_CARD_LIMIT:
        raise HTTPException(status_code=422, detail=BAD_REQUEST)
    return number


@router.get("/cards", response_model=CardsOut, responses=API_ERROR_RESPONSES)
def get_cards(
    request: Request,
    user_id: str = Query(...),
    limit: int = Query(DEFAULT_CARD_LIMIT, ge=1, le=MAX_CARD_LIMIT),
    db: Session = Depends(get_db),
) -> CardsOut:
    # The Query int still rejects non-integers. This also rejects forms that
    # int() would accept, such as "10.0", " 10", or a repeated limit.
    limit = _canonical_limit(request)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND)

    interest_rows = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
    user_interests = {row.interest for row in interest_rows}
    if not user_interests:
        return CardsOut(cards=[])

    like_rows = db.query(Like).filter(Like.user_id == user_id).all()
    excluded = {row.ticker for row in like_rows}
    excluded.update(row[0] for row in db.query(Dislike.ticker).filter(Dislike.user_id == user_id).all())

    links_by_ticker, tags_by_ticker = index_company_interests(db.query(CompanyInterest).all())

    names: dict[str, str] = {}
    liked_tickers = [row.ticker for row in like_rows]
    if liked_tickers:
        for company in db.query(Company).filter(Company.ticker.in_(liked_tickers)).all():
            names[company.ticker] = liked_display_name(company)

    liked = [
        LikedCompany(
            ticker=row.ticker,
            company_name=names.get(row.ticker, row.ticker),
            created_at=row.created_at,
            tags=frozenset(tags_by_ticker.get(row.ticker, ())),
        )
        for row in like_rows
    ]

    query = db.query(Company).filter(Company.status == "active")
    if excluded:
        query = query.filter(~Company.ticker.in_(excluded))
    companies = query.all()

    ordered = order_feed_cards(companies, links_by_ticker, tags_by_ticker, user_interests, liked)
    return CardsOut(cards=[CardOut(**card) for card in ordered[:limit]])
