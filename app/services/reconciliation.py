from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.cache import cache
from app.ingestion.master_data import MasterData, load_master_data, seed_master_data
from app.ingestion.readers import read_csv_dicts
from app.ingestion.sources import load_all_sources
from app.matching.engine import IssueData, MatchResult, OrderMatcher
from app.models import (
    AuditEvent,
    FieldProvenance,
    ImportBatch,
    Issue,
    Order,
    OrderLine,
    OrderLink,
    ReconciliationRun,
    SourceRecord,
    utcnow,
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _issue_key(issue: IssueData) -> str:
    raw = "|".join(
        [
            issue.issue_type,
            issue.source,
            issue.source_id,
            issue.order_canonical_id or "",
            issue.details,
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class ReconciliationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run(
        self,
        source_dir: Path,
        *,
        profile: str = "full",
        dry_run: bool = False,
        run_date: date | None = None,
    ) -> dict[str, Any]:
        run = ReconciliationRun(profile=profile, status="running")
        self.session.add(run)
        self.session.flush()

        try:
            master = load_master_data(self.session)
            if not master.customer_by_id or not master.product_by_sku:
                master = seed_master_data(self.session, source_dir)

            datasets = load_all_sources(
                source_dir,
                sku_by_name=master.sku_by_name,
                category_by_sku=master.category_by_sku,
            )
            erp_orders = self._count_erp_orders(source_dir)
            result = OrderMatcher(
                master,
                datasets,
                profile=profile,
                run_date=run_date,
                erp_order_count=erp_orders,
            ).run()

            if dry_run:
                self.session.rollback()
                return {"run_id": None, "status": "dry_run", "stats": result.stats}

            self._persist(result, run, master)
            run.status = "completed"
            run.stats = result.stats
            run.finished_at = utcnow()
            self.session.add(
                AuditEvent(
                    actor="system",
                    action="reconciliation.run",
                    entity="reconciliation_run",
                    entity_id=str(run.id),
                    payload={"profile": profile, **result.stats},
                )
            )
            self.session.commit()
            cache.invalidate()
            return {"run_id": run.id, "status": run.status, "stats": result.stats}
        except Exception as exc:
            self.session.rollback()
            failed = ReconciliationRun(profile=profile, status="failed", error=str(exc), finished_at=utcnow())
            self.session.add(failed)
            self.session.commit()
            raise

    def _count_erp_orders(self, source_dir: Path) -> int | None:
        path = source_dir / "data" / "erp" / "orders_2026.csv"
        if not path.exists():
            return None
        return len(read_csv_dicts(path, ";"))

    def _persist(self, result: MatchResult, run: ReconciliationRun, master: MasterData) -> None:
        existing_issue_status = {
            issue.issue_key: (issue.status, issue.resolution_note)
            for issue in self.session.scalars(select(Issue))
        }

        self.session.execute(delete(Issue))
        # Manual orders are user-created and use the CO-MAN-* namespace; a
        # reconciliation rebuilds only the orders derived from the five sources.
        self.session.execute(delete(Order).where(Order.is_manual.is_(False)))
        self.session.execute(delete(SourceRecord).where(SourceRecord.source_type == "canonical"))
        self.session.flush()

        order_pk_by_canonical: dict[str, int] = {}
        for canonical in result.orders:
            order = Order(
                canonical_order_id=canonical.canonical_order_id,
                customer_id=canonical.customer_id,
                customer_name=canonical.customer_name,
                order_date=canonical.order_date,
                delivery_date=canonical.delivery_date,
                status=canonical.status,
                total_rub=canonical.total_rub,
                currency=canonical.currency,
                match_confidence=canonical.match_confidence,
            )
            self.session.add(order)
            self.session.flush()
            order_pk_by_canonical[canonical.canonical_order_id] = order.id

            for line in canonical.lines:
                self.session.add(
                    OrderLine(
                        order_id=order.id,
                        source_type=line.source_type,
                        source_id=line.source_id,
                        line_no=line.line_no,
                        sku=line.sku,
                        product_name=line.product_name,
                        qty=line.qty,
                        unit=line.unit,
                        qty_m=line.qty_m,
                        price_rub=line.price_rub,
                        amount_rub=line.amount_rub,
                    )
                )
            for link in canonical.links:
                self.session.add(
                    OrderLink(
                        order_id=order.id,
                        source_type=link.source_type,
                        source_id=link.source_id,
                        match_method=link.match_method,
                        confidence=link.confidence,
                        is_primary=link.is_primary,
                    )
                )
            for provenance in canonical.provenance.values():
                self.session.add(
                    FieldProvenance(
                        order_id=order.id,
                        field=provenance.field,
                        source_type=provenance.source_type,
                        source_id=provenance.source_id,
                        value={"value": provenance.value},
                        confidence=provenance.confidence,
                    )
                )

            self.session.add(
                SourceRecord(
                    batch_id=None,
                    source_type="canonical",
                    source_id=canonical.canonical_order_id,
                    record_key=canonical.canonical_order_id,
                    payload={"links": [link.source_id for link in canonical.links]},
                    normalized={"status": canonical.status, "total_rub": str(canonical.total_rub)},
                )
            )

        issue_counts: dict[str, int] = {}
        for issue in result.issues:
            key = _issue_key(issue)
            status, note = existing_issue_status.get(key, ("open", None))
            self.session.add(
                Issue(
                    issue_key=key,
                    issue_type=issue.issue_type,
                    severity=issue.severity,
                    source=issue.source,
                    source_id=issue.source_id,
                    order_canonical_id=issue.order_canonical_id,
                    order_id=order_pk_by_canonical.get(issue.order_canonical_id or ""),
                    details=issue.details,
                    status=status,
                    resolution_note=note,
                    resolved_at=utcnow() if status in {"resolved", "ignored"} else None,
                )
            )
            if issue.order_canonical_id:
                issue_counts[issue.order_canonical_id] = issue_counts.get(issue.order_canonical_id, 0) + 1

        for canonical_id, count in issue_counts.items():
            order_pk = order_pk_by_canonical.get(canonical_id)
            if order_pk is not None:
                order = self.session.get(Order, order_pk)
                if order is not None:
                    order.issue_count = count

        for dataset in result.datasets.values():
            batch = ImportBatch(
                run_id=run.id,
                source_type=dataset.source_type,
                filename=dataset.filename,
                sha256=dataset.sha256,
                row_count=dataset.row_count,
            )
            self.session.add(batch)
            self.session.flush()
            for record in dataset.orders:
                self.session.add(
                    SourceRecord(
                        batch_id=batch.id,
                        source_type=dataset.source_type,
                        source_id=record.source_id,
                        record_key=record.record_key,
                        payload={key: _jsonable(value) for key, value in record.payload.items()},
                        normalized={
                            "status": record.status,
                            "order_date": _jsonable(record.order_date),
                            "delivery_date": _jsonable(record.delivery_date),
                            "total": _jsonable(record.total),
                            "duplicate": record.is_duplicate,
                        },
                        status="duplicate" if record.is_duplicate else "accepted",
                    )
                )
            for line in dataset.lines:
                self.session.add(
                    SourceRecord(
                        batch_id=batch.id,
                        source_type=f"{dataset.source_type}:line",
                        source_id=line.source_id,
                        record_key=line.record_key,
                        payload={key: _jsonable(value) for key, value in line.payload.items()},
                        normalized={
                            "sku": line.sku,
                            "qty": _jsonable(line.qty),
                            "unit": line.unit,
                            "qty_m": _jsonable(line.qty_m),
                            "flags": list(line.flags),
                        },
                    )
                )
        self.session.flush()

    def stats(self) -> dict[str, Any]:
        return {
            "orders": self.session.scalar(select(func.count()).select_from(Order)) or 0,
            "issues": self.session.scalar(select(func.count()).select_from(Issue)) or 0,
            "open_issues": self.session.scalar(
                select(func.count()).select_from(Issue).where(Issue.status == "open")
            )
            or 0,
            "imports": self.session.scalar(select(func.count()).select_from(ImportBatch)) or 0,
        }
