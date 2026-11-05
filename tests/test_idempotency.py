from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.ingestion.master_data import seed_master_data
from app.models import Issue, Order
from app.services.reconciliation import ReconciliationService

pytestmark = pytest.mark.integration


def test_second_reconciliation_keeps_ids_and_resolutions(db, full_dataset) -> None:
    seed_master_data(db, full_dataset)
    db.add(
        Order(
            canonical_order_id="CO-MAN-TEST",
            customer_name="ООО «Ручной заказ»",
            order_date=date(2026, 11, 1),
            status="new",
            total_rub=Decimal("1.00"),
            currency="RUB",
            match_confidence=Decimal("1.00"),
            is_manual=True,
        )
    )
    db.commit()
    service = ReconciliationService(db)

    first = service.run(full_dataset, profile="full", run_date=date(2026, 11, 5))
    order_ids_first = {order.canonical_order_id for order in db.scalars(select(Order))}
    issue_keys_first = {issue.issue_key for issue in db.scalars(select(Issue))}
    assert first["stats"]["orders"] == 580
    assert db.scalar(select(func.count()).select_from(Order)) == 581

    issue = db.scalar(select(Issue).order_by(Issue.id))
    assert issue is not None
    issue.status = "resolved"
    issue.resolution_note = "ручной разбор"
    db.commit()
    resolved_key = issue.issue_key

    second = service.run(full_dataset, profile="full", run_date=date(2026, 11, 5))
    order_ids_second = {order.canonical_order_id for order in db.scalars(select(Order))}
    issue_keys_second = {issue.issue_key for issue in db.scalars(select(Issue))}

    assert second["stats"]["orders"] == 580
    assert db.scalar(select(func.count()).select_from(Order)) == 581
    assert order_ids_first == order_ids_second
    assert "CO-MAN-TEST" in order_ids_second
    assert issue_keys_first == issue_keys_second

    preserved = db.scalar(select(Issue).where(Issue.issue_key == resolved_key))
    assert preserved is not None
    assert preserved.status == "resolved"
    assert preserved.resolution_note == "ручной разбор"

    manual = db.scalar(select(Order).where(Order.canonical_order_id == "CO-MAN-TEST"))
    assert manual is not None
    assert manual.is_manual is True
