from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import UserContext, require_analyst
from app.cache import cache
from app.db import get_db
from app.models import AuditEvent, Issue
from app.schemas import IssueAction, IssueOut, Page

router = APIRouter(prefix="/api/v1/issues", tags=["issues"])


@router.get("", response_model=Page[IssueOut])
def list_issues(
    status: str | None = None,
    issue_type: str | None = None,
    order_canonical_id: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[IssueOut]:
    stmt = select(Issue)
    if status:
        stmt = stmt.where(Issue.status == status)
    if issue_type:
        stmt = stmt.where(Issue.issue_type == issue_type)
    if order_canonical_id:
        stmt = stmt.where(Issue.order_canonical_id == order_canonical_id)
    if source:
        stmt = stmt.where(Issue.source == source)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Issue.source_id.ilike(pattern), Issue.details.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(stmt.order_by(Issue.severity, Issue.issue_type, Issue.id).offset(offset).limit(limit))
    )
    return Page[IssueOut](
        items=[IssueOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{issue_id}", response_model=IssueOut)
def get_issue(issue_id: int, db: Session = Depends(get_db)) -> IssueOut:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return IssueOut.model_validate(issue)


def _set_status(
    issue_id: int,
    new_status: str,
    note: str | None,
    db: Session,
    user: UserContext,
) -> IssueOut:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    previous = issue.status
    issue.status = new_status
    issue.resolution_note = note
    issue.resolved_at = datetime.now(UTC) if new_status in {"resolved", "ignored"} else None
    db.add(
        AuditEvent(
            actor=user.username,
            action=f"issue.{new_status}",
            entity="issue",
            entity_id=str(issue_id),
            payload={"from": previous, "to": new_status, "note": note},
        )
    )
    db.commit()
    cache.invalidate()
    return IssueOut.model_validate(issue)


@router.post("/{issue_id}/resolve", response_model=IssueOut)
def resolve_issue(
    issue_id: int,
    payload: IssueAction,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_analyst),
) -> IssueOut:
    return _set_status(issue_id, "resolved", payload.note, db, user)


@router.post("/{issue_id}/ignore", response_model=IssueOut)
def ignore_issue(
    issue_id: int,
    payload: IssueAction,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_analyst),
) -> IssueOut:
    return _set_status(issue_id, "ignored", payload.note, db, user)


@router.post("/{issue_id}/reopen", response_model=IssueOut)
def reopen_issue(
    issue_id: int,
    payload: IssueAction,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_analyst),
) -> IssueOut:
    return _set_status(issue_id, "open", payload.note, db, user)
