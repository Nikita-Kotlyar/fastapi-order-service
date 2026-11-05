from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.ingestion.readers import file_sha256, read_csv_dicts, read_json, read_xlsx_dicts
from app.normalization.dates import ParsedDate, parse_date
from app.normalization.money import parse_money
from app.normalization.names import normalize_name, normalize_sku
from app.normalization.statuses import (
    CRM_STAGE_TO_STATUS,
    PRODUCTION_STATUS_TO_CANONICAL,
    WAREHOUSE_STATUS_TO_CANONICAL,
    normalize_status,
)
from app.normalization.units import normalize_quantity

S_1C = "1c_orders"
S_1C_LINES = "1c_order_lines"
S_CRM = "crm_deals"
S_EMAIL = "email_orders"
S_PRODUCTION = "production_orders"
S_WAREHOUSE = "warehouse_requests"


@dataclass
class NormalizedOrderRecord:
    source_type: str
    source_id: str
    record_key: str
    row_index: int
    order_ref: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    order_date: date | None = None
    delivery_date: date | None = None
    status_raw: str | None = None
    status: str | None = None
    total: Decimal | None = None
    currency: str = "RUB"
    payload: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of: str | None = None


@dataclass
class NormalizedLineRecord:
    source_type: str
    source_id: str
    record_key: str
    line_no: int
    sku_raw: str
    sku: str
    product_name: str
    qty_raw: str
    qty: Decimal | None
    unit_raw: str
    unit: str
    qty_m: Decimal | None
    factor_to_m: Decimal | None
    price: Decimal | None
    amount: Decimal | None
    flags: tuple[str, ...]
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def negative_qty(self) -> bool:
        return self.qty is not None and self.qty < 0


@dataclass
class SourceDataset:
    source_type: str
    path: Path
    sha256: str
    row_count: int
    orders: list[NormalizedOrderRecord] = field(default_factory=list)
    lines: list[NormalizedLineRecord] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return self.path.name


def _date_parts(parsed: ParsedDate, warnings: list[str], field_name: str) -> date | None:
    if parsed.ambiguous:
        warnings.append(f"ambiguous_date:{field_name}")
    if parsed.value is None and parsed.error not in (None, "empty"):
        warnings.append(f"invalid_date:{field_name}")
    return parsed.value


def _fingerprint(*values: object) -> str:
    raw = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_1c_orders(path: Path) -> SourceDataset:
    rows = read_csv_dicts(path, ";")
    dataset = SourceDataset(S_1C, path, file_sha256(path), len(rows))
    grouped: dict[str, list[NormalizedOrderRecord]] = {}

    for index, row in enumerate(rows, start=1):
        warnings: list[str] = []
        order_id = (row.get("order_id") or "").strip()
        order_date = _date_parts(parse_date(row.get("order_date")), warnings, "order_date")
        delivery_date = _date_parts(parse_date(row.get("delivery_date")), warnings, "delivery_date")
        status_raw = (row.get("status") or "").strip()
        status = normalize_status(status_raw)
        total = parse_money(row.get("total_rub"))
        record = NormalizedOrderRecord(
            source_type=S_1C,
            source_id=order_id,
            record_key=f"{order_id}#{index}",
            row_index=index,
            order_ref=order_id,
            customer_id=(row.get("customer_id") or "").strip() or None,
            customer_name=(row.get("customer_name") or "").strip() or None,
            order_date=order_date,
            delivery_date=delivery_date,
            status_raw=status_raw,
            status=status,
            total=total,
            currency=(row.get("currency") or "RUB").strip() or "RUB",
            payload=row,
            warnings=warnings,
        )
        grouped.setdefault(order_id, []).append(record)

    for order_id, records in grouped.items():
        primary = next(
            (record for record in records if "дубль" not in str(record.payload.get("comment", "")).lower()),
            records[0],
        )
        dataset.orders.append(primary)
        for record in records:
            if record is primary:
                continue
            record.is_duplicate = True
            record.duplicate_of = order_id
            dataset.orders.append(record)
    return dataset


def load_1c_lines(
    path: Path,
    *,
    sku_by_name: dict[str, str] | None = None,
    category_by_sku: dict[str, str] | None = None,
) -> SourceDataset:
    rows = read_csv_dicts(path, ";")
    dataset = SourceDataset(S_1C_LINES, path, file_sha256(path), len(rows))
    line_counters: dict[str, int] = {}

    for row in rows:
        order_id = (row.get("order_id") or "").strip()
        line_counters[order_id] = line_counters.get(order_id, 0) + 1
        sku_raw = (row.get("sku") or "").strip()
        sku = normalize_sku(sku_raw)
        product_name = (row.get("product_name") or "").strip()
        flags: list[str] = []

        resolved_sku = sku
        if sku_by_name and normalize_name(product_name) in sku_by_name:
            resolved_sku = sku_by_name[normalize_name(product_name)]
            if resolved_sku != sku:
                flags.append("unknown_sku_resolved")
        elif category_by_sku is not None and sku not in category_by_sku:
            flags.append("unknown_sku")

        category = (category_by_sku or {}).get(resolved_sku)
        quantity = normalize_quantity(row.get("qty"), row.get("unit"), category=category)
        flags.extend(quantity.flags)

        dataset.lines.append(
            NormalizedLineRecord(
                source_type=S_1C_LINES,
                source_id=order_id,
                record_key=f"{order_id}#{line_counters[order_id]}",
                line_no=line_counters[order_id],
                sku_raw=sku_raw,
                sku=resolved_sku,
                product_name=product_name,
                qty_raw=str(row.get("qty") or ""),
                qty=quantity.qty,
                unit_raw=(row.get("unit") or "").strip(),
                unit=quantity.unit,
                qty_m=quantity.qty_m,
                factor_to_m=quantity.factor_to_m,
                price=parse_money(row.get("price_rub")),
                amount=parse_money(row.get("amount_rub")),
                flags=tuple(dict.fromkeys(flags)),
                payload=row,
            )
        )
    return dataset


def load_crm_deals(path: Path) -> SourceDataset:
    rows = read_json(path)
    dataset = SourceDataset(S_CRM, path, file_sha256(path), len(rows))
    seen: dict[str, str] = {}

    for index, row in enumerate(rows, start=1):
        warnings: list[str] = []
        deal_id = str(row.get("deal_id") or "").strip()
        stage_raw = str(row.get("stage") or "").strip().lower()
        created = _date_parts(parse_date(row.get("created_at")), warnings, "created_at")
        amount = parse_money(row.get("amount"))
        fingerprint = _fingerprint(
            row.get("customer_id"),
            row.get("customer_name"),
            amount,
            row.get("source_order"),
            row.get("created_at"),
        )
        is_duplicate = fingerprint in seen
        duplicate_of = seen.get(fingerprint)
        if not is_duplicate:
            seen[fingerprint] = deal_id

        dataset.orders.append(
            NormalizedOrderRecord(
                source_type=S_CRM,
                source_id=deal_id,
                record_key=deal_id or f"row-{index}",
                row_index=index,
                order_ref=str(row.get("source_order") or "").strip() or None,
                customer_id=str(row.get("customer_id") or "").strip() or None,
                customer_name=str(row.get("customer_name") or "").strip() or None,
                order_date=created,
                status_raw=stage_raw,
                status=CRM_STAGE_TO_STATUS.get(stage_raw, "new"),
                total=amount,
                payload=row,
                warnings=warnings,
                is_duplicate=is_duplicate,
                duplicate_of=duplicate_of,
            )
        )
    return dataset


def _strip_order_ref(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"б/н", "бн", "нет", "unknown"}:
        return None
    for prefix in ("№", "no.", "no", "#"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    return text or None


def load_email_orders(path: Path) -> SourceDataset:
    rows = read_xlsx_dicts(path)
    dataset = SourceDataset(S_EMAIL, path, file_sha256(path), len(rows))
    for index, row in enumerate(rows, start=1):
        warnings: list[str] = []
        email_id = str(row.get("email_id") or "").strip()
        order_ref = _strip_order_ref(row.get("order_ref"))
        order_date = _date_parts(parse_date(row.get("order_date")), warnings, "order_date")
        price = parse_money(row.get("price"))
        dataset.orders.append(
            NormalizedOrderRecord(
                source_type=S_EMAIL,
                source_id=email_id,
                record_key=email_id or f"row-{index}",
                row_index=index,
                order_ref=order_ref,
                customer_name=str(row.get("customer") or "").strip() or None,
                order_date=order_date,
                status_raw="new",
                status="new",
                # Email prices are quoted per 1000 m in the source extracts; this is a
                # display total for email-only requests, not a replacement for 1C money.
                total=(price * 1000) if price is not None else None,
                payload=row,
                warnings=warnings,
            )
        )
    return dataset


def load_production_orders(path: Path) -> SourceDataset:
    rows = read_csv_dicts(path, ";")
    dataset = SourceDataset(S_PRODUCTION, path, file_sha256(path), len(rows))
    for index, row in enumerate(rows, start=1):
        warnings: list[str] = []
        order_ref = str(row.get("order_ref") or "").strip()
        planned_end = _date_parts(parse_date(row.get("planned_end")), warnings, "planned_end")
        status_raw = str(row.get("status") or "").strip().lower()
        dataset.orders.append(
            NormalizedOrderRecord(
                source_type=S_PRODUCTION,
                source_id=order_ref,
                record_key=f"{order_ref}#{index}",
                row_index=index,
                order_ref=order_ref,
                delivery_date=planned_end,
                status_raw=status_raw,
                status=PRODUCTION_STATUS_TO_CANONICAL.get(status_raw, "confirmed"),
                payload=row,
                warnings=warnings,
            )
        )
        if row.get("sku") and row.get("qty") is not None:
            quantity = normalize_quantity(row.get("qty"), row.get("unit"))
            dataset.lines.append(
                NormalizedLineRecord(
                    source_type=S_PRODUCTION,
                    source_id=order_ref,
                    record_key=f"{order_ref}#{index}",
                    line_no=1,
                    sku_raw=str(row.get("sku") or "").strip(),
                    sku=normalize_sku(str(row.get("sku") or "")),
                    product_name="",
                    qty_raw=str(row.get("qty") or ""),
                    qty=quantity.qty,
                    unit_raw=str(row.get("unit") or "").strip(),
                    unit=quantity.unit,
                    qty_m=quantity.qty_m,
                    factor_to_m=quantity.factor_to_m,
                    price=None,
                    amount=None,
                    flags=quantity.flags,
                    payload=row,
                )
            )
    return dataset


def load_warehouse_requests(path: Path) -> SourceDataset:
    rows = read_csv_dicts(path, ";")
    dataset = SourceDataset(S_WAREHOUSE, path, file_sha256(path), len(rows))
    seen: dict[str, str] = {}
    for index, row in enumerate(rows, start=1):
        warnings: list[str] = []
        request_id = str(row.get("request_id") or "").strip()
        ship_date = _date_parts(parse_date(row.get("ship_date")), warnings, "ship_date")
        status_raw = str(row.get("status") or "").strip().lower()
        is_duplicate = request_id in seen
        duplicate_of = seen.get(request_id)
        if not is_duplicate:
            seen[request_id] = request_id
        dataset.orders.append(
            NormalizedOrderRecord(
                source_type=S_WAREHOUSE,
                source_id=request_id,
                record_key=f"{request_id}#{index}",
                row_index=index,
                order_ref=str(row.get("order_ref") or "").strip() or None,
                delivery_date=ship_date,
                status_raw=status_raw,
                status=WAREHOUSE_STATUS_TO_CANONICAL.get(status_raw, "confirmed"),
                payload=row,
                warnings=warnings,
                is_duplicate=is_duplicate,
                duplicate_of=duplicate_of,
            )
        )
        quantity = normalize_quantity(row.get("qty"), row.get("unit"))
        dataset.lines.append(
            NormalizedLineRecord(
                source_type=S_WAREHOUSE,
                source_id=request_id,
                record_key=f"{request_id}#{index}",
                line_no=1,
                sku_raw=str(row.get("sku") or "").strip(),
                sku=normalize_sku(str(row.get("sku") or "")),
                product_name="",
                qty_raw=str(row.get("qty") or ""),
                qty=quantity.qty,
                unit_raw=str(row.get("unit") or "").strip(),
                unit=quantity.unit,
                qty_m=quantity.qty_m,
                factor_to_m=quantity.factor_to_m,
                price=None,
                amount=None,
                flags=quantity.flags,
                payload=row,
            )
        )
    return dataset


def load_all_sources(
    source_dir: Path,
    *,
    sku_by_name: dict[str, str] | None = None,
    category_by_sku: dict[str, str] | None = None,
) -> dict[str, SourceDataset]:
    integration = source_dir / "data" / "integration"
    files = {
        S_1C: integration / "1c_orders_export.csv",
        S_1C_LINES: integration / "1c_order_lines_export.csv",
        S_CRM: integration / "crm_deals_export.json",
        S_EMAIL: integration / "sales_orders_from_email.xlsx",
        S_PRODUCTION: integration / "production_orders_export.csv",
        S_WAREHOUSE: integration / "warehouse_shipment_requests.csv",
    }
    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Не найдены источники: " + ", ".join(missing))

    return {
        S_1C: load_1c_orders(files[S_1C]),
        S_1C_LINES: load_1c_lines(
            files[S_1C_LINES], sku_by_name=sku_by_name, category_by_sku=category_by_sku
        ),
        S_CRM: load_crm_deals(files[S_CRM]),
        S_EMAIL: load_email_orders(files[S_EMAIL]),
        S_PRODUCTION: load_production_orders(files[S_PRODUCTION]),
        S_WAREHOUSE: load_warehouse_requests(files[S_WAREHOUSE]),
    }
