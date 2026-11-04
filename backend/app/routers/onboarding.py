"""Create a user from the interests they picked. No login in Milestone 1."""

from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db, utcnow
from app.interests import ALLOWED_INTERESTS
from app.models import User, UserInterest
from app.schemas import OnboardingIn, OnboardingOut

router = APIRouter()

ALLOWED = set(ALLOWED_INTERESTS)


@router.post("/onboarding", response_model=OnboardingOut)
def onboarding(body: OnboardingIn, db: Session = Depends(get_db)) -> OnboardingOut:
    chosen: list[str] = []
    for raw in body.interests:
        interest = str(raw).strip().lower()
        if interest not in ALLOWED:
            allowed = ", ".join(ALLOWED_INTERESTS)
            raise HTTPException(
                status_code=400,
                detail=f"Unknown interest '{interest}'. Choose from: {allowed}.",
            )
        if interest not in chosen:
            chosen.append(interest)

    if not chosen:
        raise HTTPException(status_code=400, detail="Pick at least one interest.")

    user = User(id=str(uuid.uuid4()), created_at=utcnow())
    db.add(user)
    db.flush()
    for interest in chosen:
        db.add(UserInterest(user_id=user.id, interest=interest))
    db.commit()
    return OnboardingOut(user_id=user.id)
