from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import UserContext, require_analyst
from app.config import settings
from app.db import get_db
from app.models import ImportBatch, ReconciliationRun, SourceRecord
from app.schemas import (
    ImportBatchOut,
    Page,
    ReconciliationRequest,
    ReconciliationRunOut,
    SourceRecordOut,
)
from app.services.reconciliation import ReconciliationService

router = APIRouter(prefix="/api/v1", tags=["imports"])


@router.post("/reconciliation/runs")
def start_reconciliation(
    payload: ReconciliationRequest,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_analyst),
) -> dict:
    service = ReconciliationService(db)
    return service.run(
        settings.source_dir,
        profile=payload.profile,
        dry_run=payload.dry_run,
        run_date=payload.run_date,
    )


@router.get("/reconciliation/runs", response_model=Page[ReconciliationRunOut])
def list_runs(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ReconciliationRunOut]:
    stmt = select(ReconciliationRun)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(ReconciliationRun.id.desc()).offset(offset).limit(limit)))
    return Page[ReconciliationRunOut](
        items=[ReconciliationRunOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/reconciliation/runs/{run_id}", response_model=ReconciliationRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)) -> ReconciliationRunOut:
    run = db.get(ReconciliationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return ReconciliationRunOut.model_validate(run)


@router.get("/imports", response_model=Page[ImportBatchOut])
def list_imports(
    source_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ImportBatchOut]:
    stmt = select(ImportBatch)
    if source_type:
        stmt = stmt.where(ImportBatch.source_type == source_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(ImportBatch.id.desc()).offset(offset).limit(limit)))
    return Page[ImportBatchOut](
        items=[ImportBatchOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/imports/{batch_id}/records", response_model=Page[SourceRecordOut])
def list_import_records(
    batch_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[SourceRecordOut]:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    stmt = select(SourceRecord).where(SourceRecord.batch_id == batch_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(SourceRecord.id).offset(offset).limit(limit)))
    return Page[SourceRecordOut](
        items=[SourceRecordOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
