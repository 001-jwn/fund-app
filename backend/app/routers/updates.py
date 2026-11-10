"""Cached lines for stocks the user already likes. Reads the database only."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert, Company, Match, User
from app.schemas import AlertOut, FilingOut, UpdateOut, UpdatesOut
from app.services.cards import liked_display_name
from app.services.catalysts import NEW_YORK, detect_for_user, earnings_alert_is_current
from app.services.digest import build_digest
from app.services.sec_filings import filings_for_user
from app.services.updates import build_update

logger = logging.getLogger("fund.updates")
ALERT_CAP = 50

router = APIRouter()


@router.get("/updates", response_model=UpdatesOut)
def get_updates(user_id: str = Query(...), db: Session = Depends(get_db)) -> UpdatesOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        detect_for_user(db, user_id)
        db.commit()
    except Exception:
        logger.exception("Catalyst detection failed for %s", user_id)
        db.rollback()

    rows = (
        db.query(Match)
        .filter(Match.user_id == user_id)
        .order_by(Match.created_at.desc(), Match.ticker)
        .all()
    )

    updates: list[UpdateOut] = []
    liked_companies: list[Company] = []
    for match in rows:
        try:
            company = db.get(Company, match.ticker)
        except (ArithmeticError, ValueError, TypeError, OverflowError):
            continue
        if company is None:
            continue
        liked_companies.append(company)
        try:
            item = build_update(company)
        except (ArithmeticError, ValueError, TypeError, OverflowError, OSError):
            continue
        if item is None:
            continue
        updates.append(UpdateOut(**item))
    alerts, unseen_count = _alerts_for_user(db, user_id)
    digest = build_digest(liked_companies, has_likes=bool(rows))
    return UpdatesOut(
        updates=updates,
        alerts=alerts,
        unseen_count=unseen_count,
        digest=digest,
        filings=[FilingOut(**item) for item in filings_for_user(db, user_id)],
    )


def _alerts_for_user(db: Session, user_id: str) -> tuple[list[AlertOut], int]:
    liked = {row[0] for row in db.query(Match.ticker).filter(Match.user_id == user_id).all()}
    if not liked:
        return [], 0
    rows = (
        db.query(Alert)
        .filter(Alert.user_id == user_id, Alert.ticker.in_(liked))
        .order_by(Alert.created_at.desc(), Alert.id.desc())
        .all()
    )
    today_et = datetime.now(NEW_YORK).date()
    rows = [row for row in rows if earnings_alert_is_current(row.kind, row.facts, today_et)]
    unseen = sum(1 for row in rows if not row.seen)
    alerts: list[AlertOut] = []
    for row in rows[:ALERT_CAP]:
        company = db.get(Company, row.ticker)
        if company is None:
            continue
        url = None
        if row.kind == "news":
            try:
                url = json.loads(row.facts or "{}").get("url")
            except json.JSONDecodeError:
                url = None
        created = row.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        alerts.append(
            AlertOut(
                id=row.id,
                ticker=row.ticker,
                short_name=liked_display_name(company),
                kind=row.kind,
                line=row.line,
                created_at=created.isoformat() if created is not None else "",
                seen=bool(row.seen),
                url=url if isinstance(url, str) and url.strip() else None,
            )
        )
    return alerts, unseen
