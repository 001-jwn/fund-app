"""Like creates a match. Dislike hides the company and drops a match. Unlike drops a match only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.models import (
    Alert,
    AlertBaseline,
    Company,
    CompanyInterest,
    Dislike,
    Like,
    Match,
    User,
    UserInterest,
)
from app.schemas import SwipeIn, SwipeOut

router = APIRouter()


def _user_and_company(db: Session, user_id: str, ticker: str) -> tuple[User, Company, str]:
    ticker = ticker.strip().upper()
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    company = db.get(Company, ticker)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    if company.status != "active":
        raise HTTPException(status_code=400, detail="That company is not active.")
    _require_user_interest(db, user_id, ticker)
    return user, company, ticker


def _known_user_and_company(db: Session, user_id: str, ticker: str) -> tuple[User, Company, str]:
    """User and company must exist. No interest check and no active check."""
    ticker = ticker.strip().upper()
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    company = db.get(Company, ticker)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return user, company, ticker


def _require_user_interest(db: Session, user_id: str, ticker: str) -> None:
    user_interests = {
        row.interest for row in db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
    }
    company_interests = {
        row.interest for row in db.query(CompanyInterest).filter(CompanyInterest.ticker == ticker).all()
    }
    if not user_interests.intersection(company_interests):
        raise HTTPException(
            status_code=400,
            detail="That company is outside the interests you picked.",
        )


@router.post("/like", response_model=SwipeOut)
def like(body: SwipeIn, db: Session = Depends(get_db)) -> SwipeOut:
    _user, _company, ticker = _user_and_company(db, body.user_id, body.ticker)

    db.query(Dislike).filter(Dislike.user_id == body.user_id, Dislike.ticker == ticker).delete(
        synchronize_session=False
    )
    if db.get(Like, (body.user_id, ticker)) is None:
        db.add(Like(user_id=body.user_id, ticker=ticker, created_at=utcnow()))
    if db.get(Match, (body.user_id, ticker)) is None:
        db.add(Match(user_id=body.user_id, ticker=ticker, created_at=utcnow()))
    db.commit()
    return SwipeOut(ok=True, user_id=body.user_id, ticker=ticker, matched=True)


@router.post("/dislike", response_model=SwipeOut)
def dislike(body: SwipeIn, db: Session = Depends(get_db)) -> SwipeOut:
    _user, _company, ticker = _user_and_company(db, body.user_id, body.ticker)

    db.query(Like).filter(Like.user_id == body.user_id, Like.ticker == ticker).delete(
        synchronize_session=False
    )
    db.query(Match).filter(Match.user_id == body.user_id, Match.ticker == ticker).delete(
        synchronize_session=False
    )
    if db.get(Dislike, (body.user_id, ticker)) is None:
        db.add(Dislike(user_id=body.user_id, ticker=ticker, created_at=utcnow()))
    db.commit()
    return SwipeOut(ok=True, user_id=body.user_id, ticker=ticker, matched=False)


@router.post("/unlike", response_model=SwipeOut)
def unlike(body: SwipeIn, db: Session = Depends(get_db)) -> SwipeOut:
    _user, _company, ticker = _known_user_and_company(db, body.user_id, body.ticker)

    db.query(Like).filter(Like.user_id == body.user_id, Like.ticker == ticker).delete(
        synchronize_session=False
    )
    db.query(Match).filter(Match.user_id == body.user_id, Match.ticker == ticker).delete(
        synchronize_session=False
    )
    db.query(Alert).filter(Alert.user_id == body.user_id, Alert.ticker == ticker).delete(
        synchronize_session=False
    )
    db.query(AlertBaseline).filter(
        AlertBaseline.user_id == body.user_id, AlertBaseline.ticker == ticker
    ).delete(synchronize_session=False)
    db.commit()
    return SwipeOut(ok=True, user_id=body.user_id, ticker=ticker, matched=False)
