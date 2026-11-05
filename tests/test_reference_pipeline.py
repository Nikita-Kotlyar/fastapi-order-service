from __future__ import annotations

from datetime import date

from sqlalchemy import func, select

from app.ingestion.master_data import seed_master_data
from app.models import Issue, Order
from app.services.reconciliation import ReconciliationService

EXPECTED_SOURCES = {
    "1c_orders": 10,
    "crm_deals": 9,
    "email_orders": 5,
    "production_orders": 7,
    "warehouse_requests": 5,
}

EXPECTED_ISSUES = {
    "duplicate_1c": 1,
    "status_conflict": 1,
    "unit_mismatch": 6,
    "missing_customer": 2,
    "unknown_sku": 1,
    "total_mismatch": 1,
    "negative_qty": 1,
    "mixed_unit": 1,
    "missing_conversion": 1,
    "duplicate_crm": 1,
    "duplicate_warehouse": 1,
    "orphan_production": 2,
    "orphan_warehouse": 1,
    "email_only": 2,
    "contradictory_conversion": 1,
    "coverage_gap": 1,
    "ambiguous_date": 2,
}


def test_reference_pipeline(db, reference_dataset) -> None:
    seed_master_data(db, reference_dataset)
    db.commit()
    service = ReconciliationService(db)

    first = service.run(reference_dataset, profile="full", run_date=date(2026, 11, 5))
    stats = first["stats"]
    assert stats["orders"] == 16
    assert stats["by_source"] == EXPECTED_SOURCES

    counts = {
        issue_type: count
        for issue_type, count in db.execute(select(Issue.issue_type, func.count()).group_by(Issue.issue_type))
    }
    for issue_type, expected in EXPECTED_ISSUES.items():
        assert counts.get(issue_type, 0) == expected, (issue_type, counts.get(issue_type, 0), expected)

    second = service.run(reference_dataset, profile="full", run_date=date(2026, 11, 5))
    assert second["stats"]["orders"] == 16
    assert db.scalar(select(func.count()).select_from(Order)) == 16
    assert db.scalar(select(func.count()).select_from(Issue)) == sum(EXPECTED_ISSUES.values())
