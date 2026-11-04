"""Swipe cards for one user's interests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, CompanyInterest, Dislike, Like, User, UserInterest
from app.schemas import CardOut, CardsOut
from app.services.cards import LikedCompany, index_company_interests, order_feed_cards

router = APIRouter()


@router.get("/cards", response_model=CardsOut)
def get_cards(
    user_id: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> CardsOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

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
            names[company.ticker] = company.company_name

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
