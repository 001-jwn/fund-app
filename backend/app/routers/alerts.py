"""Mark catalyst alerts as seen. Does not delete them."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert, User
from app.schemas import AlertsSeenIn, AlertsSeenOut

router = APIRouter()


@router.post("/alerts/seen", response_model=AlertsSeenOut)
def mark_alerts_seen(body: AlertsSeenIn, db: Session = Depends(get_db)) -> AlertsSeenOut:
    user = db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    db.query(Alert).filter(Alert.user_id == body.user_id, Alert.seen.is_(False)).update(
        {Alert.seen: True},
        synchronize_session=False,
    )
    db.commit()
    return AlertsSeenOut(unseen_count=0)
