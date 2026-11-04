"""Swipe cards for one user's interests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, CompanyInterest, Dislike, Like, User, UserInterest
from app.schemas import CardOut, CardsOut
from app.services.cards import choose_interest_link, public_card

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

    excluded = {row[0] for row in db.query(Like.ticker).filter(Like.user_id == user_id).all()}
    excluded.update(row[0] for row in db.query(Dislike.ticker).filter(Dislike.user_id == user_id).all())

    query = db.query(Company).filter(Company.status == "active")
    if excluded:
        query = query.filter(~Company.ticker.in_(excluded))
    companies = query.order_by(Company.ticker).all()

    cards: list[CardOut] = []
    for company in companies:
        links = db.query(CompanyInterest).filter(CompanyInterest.ticker == company.ticker).all()
        link = choose_interest_link(links, user_interests)
        if link is None:
            continue
        cards.append(CardOut(**public_card(company, link)))
        if len(cards) >= limit:
            break

    return CardsOut(cards=cards)
