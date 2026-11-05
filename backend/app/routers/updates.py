"""Cached lines for stocks the user already likes. Reads the database only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, Match, User
from app.schemas import UpdateOut, UpdatesOut
from app.services.updates import build_update

router = APIRouter()


@router.get("/updates", response_model=UpdatesOut)
def get_updates(user_id: str = Query(...), db: Session = Depends(get_db)) -> UpdatesOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    rows = (
        db.query(Match)
        .filter(Match.user_id == user_id)
        .order_by(Match.created_at.desc(), Match.ticker)
        .all()
    )

    updates: list[UpdateOut] = []
    for match in rows:
        company = db.get(Company, match.ticker)
        if company is None:
            continue
        item = build_update(company)
        if item is None:
            continue
        updates.append(UpdateOut(**item))
    return UpdatesOut(updates=updates)
