from __future__ import annotations

import pytest

from app.ingestion.sources import (
    load_1c_lines,
    load_1c_orders,
    load_crm_deals,
    load_email_orders,
    load_production_orders,
    load_warehouse_requests,
)

pytestmark = pytest.mark.integration


def test_1c_orders_keep_primary_and_duplicates(full_dataset) -> None:
    dataset = load_1c_orders(full_dataset / "data/integration/1c_orders_export.csv")
    assert dataset.row_count == 450
    assert len(dataset.orders) == 450
    primary = [record for record in dataset.orders if not record.is_duplicate]
    duplicates = [record for record in dataset.orders if record.is_duplicate]
    assert len(primary) == 400
    assert len(duplicates) == 50
    assert all(record.duplicate_of in {item.source_id for item in primary} for record in duplicates)


def test_1c_lines_normalize_units(full_dataset) -> None:
    dataset = load_1c_lines(full_dataset / "data/integration/1c_order_lines_export.csv")
    assert dataset.row_count == 998
    units = {line.unit for line in dataset.lines}
    assert {"м", "км", "рулон", "барабан", "палетоместо", "упаковка", "шт", "смеш."} <= units
    assert any(line.qty_m == 8000 for line in dataset.lines)


def test_crm_duplicates_detected(full_dataset) -> None:
    dataset = load_crm_deals(full_dataset / "data/integration/crm_deals_export.json")
    assert dataset.row_count == 339
    assert sum(record.is_duplicate for record in dataset.orders) == 30
    assert sum(1 for record in dataset.orders if not record.order_ref) == 80


def test_email_and_production_counts(full_dataset) -> None:
    email = load_email_orders(full_dataset / "data/integration/sales_orders_from_email.xlsx")
    production = load_production_orders(full_dataset / "data/integration/production_orders_export.csv")
    assert email.row_count == 183
    assert production.row_count == 250
    assert sum(1 for record in email.orders if not record.order_ref) >= 50


def test_warehouse_duplicates_detected(full_dataset) -> None:
    dataset = load_warehouse_requests(full_dataset / "data/integration/warehouse_shipment_requests.csv")
    assert dataset.row_count == 240
    assert sum(record.is_duplicate for record in dataset.orders) == 25
    assert any(record.order_ref == "UNKNOWN" for record in dataset.orders)
