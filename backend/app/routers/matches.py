"""Liked companies. Every like is a match in Milestone 1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, CompanyInterest, Match, User, UserInterest
from app.schemas import MatchOut, MatchesOut
from app.services.cards import choose_interest_link, public_card

router = APIRouter()


@router.get("/matches", response_model=MatchesOut)
def get_matches(user_id: str = Query(...), db: Session = Depends(get_db)) -> MatchesOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    interest_rows = db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
    user_interests = {row.interest for row in interest_rows}

    rows = (
        db.query(Match)
        .filter(Match.user_id == user_id)
        .order_by(Match.created_at.desc(), Match.ticker)
        .all()
    )

    matches: list[MatchOut] = []
    for match in rows:
        company = db.get(Company, match.ticker)
        if company is None:
            continue
        links = db.query(CompanyInterest).filter(CompanyInterest.ticker == company.ticker).all()
        link = choose_interest_link(links, user_interests)
        if link is None and links:
            link = links[0]
        if link is None:
            continue
        payload = public_card(company, link)
        payload["matched_at"] = match.created_at.isoformat() if match.created_at else ""
        matches.append(MatchOut(**payload))

    return MatchesOut(matches=matches)
