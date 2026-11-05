from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.dq.detectors import CORE_ISSUE_TYPES, SEVERITY
from app.ingestion.master_data import MasterData
from app.ingestion.sources import (
    S_1C,
    S_1C_LINES,
    S_CRM,
    S_EMAIL,
    S_PRODUCTION,
    S_WAREHOUSE,
    NormalizedLineRecord,
    NormalizedOrderRecord,
    SourceDataset,
)
from app.matching.rules import DEFAULT_LEAD_DAYS, FUZZY_EMAIL_THRESHOLD, TOTAL_MISMATCH_TOLERANCE
from app.normalization.names import normalize_name, normalize_sku
from app.normalization.statuses import crm_stage_conflicts


@dataclass
class CanonicalLine:
    source_type: str
    source_id: str
    line_no: int
    sku: str
    product_name: str
    qty: Decimal | None
    unit: str
    qty_m: Decimal | None
    factor_to_m: Decimal | None
    price_rub: Decimal | None
    amount_rub: Decimal | None
    flags: tuple[str, ...] = ()


@dataclass
class LinkData:
    source_type: str
    source_id: str
    match_method: str
    confidence: Decimal
    is_primary: bool


@dataclass
class ProvenanceData:
    field: str
    source_type: str
    source_id: str
    value: Any
    confidence: Decimal


@dataclass
class CanonicalOrder:
    canonical_order_id: str
    customer_id: str | None
    customer_name: str
    order_date: date
    delivery_date: date | None
    status: str
    total_rub: Decimal
    currency: str
    match_confidence: Decimal
    lines: list[CanonicalLine] = field(default_factory=list)
    links: list[LinkData] = field(default_factory=list)
    provenance: dict[str, ProvenanceData] = field(default_factory=dict)


@dataclass
class IssueData:
    issue_type: str
    source: str
    source_id: str
    details: str
    order_canonical_id: str | None = None
    severity: str = "medium"


@dataclass
class MatchResult:
    orders: list[CanonicalOrder]
    issues: list[IssueData]
    stats: dict[str, Any]
    datasets: dict[str, SourceDataset]


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


class OrderMatcher:
    """Entity-resolution engine for the five order representations.

    The engine is deterministic: the same inputs produce the same canonical IDs
    and the same issue keys, which makes repeated reconciliation idempotent.
    """

    def __init__(
        self,
        master: MasterData,
        datasets: dict[str, SourceDataset],
        *,
        profile: str = "full",
        run_date: date | None = None,
        erp_order_count: int | None = None,
    ) -> None:
        self.master = master
        self.datasets = datasets
        self.profile = profile
        self.run_date = run_date or date.today()
        self.period_start = self.run_date.replace(day=1)
        self.erp_order_count = erp_order_count

        self.orders: list[CanonicalOrder] = []
        self.issues: list[IssueData] = []
        self._counter = 0
        self._order_issue_keys: set[tuple[str, str, str]] = set()
        self._by_1c: dict[str, CanonicalOrder] = {}
        self._by_any_key: dict[str, CanonicalOrder] = {}
        self._email_index: dict[tuple[str, date], list[CanonicalOrder]] = defaultdict(list)
        self._lines_by_order: dict[str, list[NormalizedLineRecord]] = defaultdict(list)

    # ------------------------------------------------------------------ public
    def run(self) -> MatchResult:
        self._index_lines()
        self._build_1c_orders()
        self._apply_crm()
        self._apply_email()
        self._apply_production()
        self._apply_warehouse()
        self._conversion_issues()
        self._coverage_issue()
        self._ambiguous_date_issues()

        issues = self.issues
        if self.profile == "reference":
            issues = [issue for issue in issues if issue.issue_type in CORE_ISSUE_TYPES]

        stats = {
            "orders": len(self.orders),
            "lines": sum(len(order.lines) for order in self.orders),
            "links": sum(len(order.links) for order in self.orders),
            "issues": len(issues),
            "by_status": dict(Counter(order.status for order in self.orders)),
            "by_issue_type": dict(Counter(issue.issue_type for issue in issues)),
            "by_source": {
                source_type: sum(
                    1 for order in self.orders for link in order.links if link.source_type == source_type
                )
                for source_type in (S_1C, S_CRM, S_EMAIL, S_PRODUCTION, S_WAREHOUSE)
            },
            "coverage": {
                "1c_unique_orders": len(self._by_1c),
                "erp_orders": self.erp_order_count,
            },
            "run_date": self.run_date.isoformat(),
            "profile": self.profile,
        }
        return MatchResult(self.orders, issues, stats, self.datasets)

    # ------------------------------------------------------------------ helpers
    def _next_id(self) -> str:
        self._counter += 1
        return f"CO-2026-{self._counter:04d}"

    def _index_lines(self) -> None:
        for line in self.datasets[S_1C_LINES].lines:
            self._lines_by_order[line.source_id].append(line)

    def _resolve_customer(self, raw_id: str | None, name: str | None) -> tuple[str | None, str]:
        if raw_id and raw_id in self.master.customer_by_id:
            return raw_id, self.master.customer_by_id[raw_id]["name"]
        normalized = normalize_name(name)
        if normalized and normalized in self.master.customer_by_name:
            return self.master.customer_by_name[normalized], name or ""
        return None, name or "Неизвестный заказчик"

    def _is_suspect_customer(
        self, raw_id: str | None, resolved_id: str | None, *, require_raw_id: bool = True
    ) -> bool:
        if resolved_id is None:
            return True
        if raw_id and raw_id.upper() == "CUST-999":
            return True
        return require_raw_id and not raw_id

    def _add_issue(
        self,
        issue_type: str,
        source: str,
        source_id: str,
        details: str,
        *,
        order: CanonicalOrder | None = None,
        once_per_order: bool = False,
    ) -> None:
        if once_per_order and order is not None:
            key = (order.canonical_order_id, issue_type, source_id)
            if key in self._order_issue_keys:
                return
            self._order_issue_keys.add(key)
        self.issues.append(
            IssueData(
                issue_type=issue_type,
                source=source,
                source_id=source_id,
                details=details,
                order_canonical_id=order.canonical_order_id if order else None,
                severity=SEVERITY.get(issue_type, "medium"),
            )
        )

    def _provenance(
        self,
        order: CanonicalOrder,
        field_name: str,
        source_type: str,
        source_id: str,
        value: Any,
        confidence: Decimal = Decimal("1.00"),
    ) -> None:
        order.provenance[field_name] = ProvenanceData(
            field=field_name,
            source_type=source_type,
            source_id=source_id,
            value=_json_value(value),
            confidence=confidence,
        )

    def _new_order(
        self,
        *,
        customer_id: str | None,
        customer_name: str,
        order_date: date,
        delivery_date: date | None,
        status: str,
        total: Decimal,
        currency: str,
        confidence: Decimal,
    ) -> CanonicalOrder:
        order = CanonicalOrder(
            canonical_order_id=self._next_id(),
            customer_id=customer_id,
            customer_name=customer_name,
            order_date=order_date,
            delivery_date=delivery_date,
            status=status,
            total_rub=total,
            currency=currency,
            match_confidence=confidence,
        )
        self.orders.append(order)
        return order

    def _link(
        self,
        order: CanonicalOrder,
        source_type: str,
        source_id: str,
        method: str,
        confidence: Decimal,
        *,
        primary: bool = False,
    ) -> None:
        if any(link.source_type == source_type and link.source_id == source_id for link in order.links):
            return
        order.links.append(
            LinkData(
                source_type=source_type,
                source_id=source_id,
                match_method=method,
                confidence=confidence,
                is_primary=primary,
            )
        )

    def _line_from_record(self, line: NormalizedLineRecord) -> CanonicalLine:
        return CanonicalLine(
            source_type=line.source_type,
            source_id=line.source_id,
            line_no=line.line_no,
            sku=line.sku,
            product_name=line.product_name,
            qty=line.qty,
            unit=line.unit,
            qty_m=line.qty_m,
            factor_to_m=line.factor_to_m,
            price_rub=line.price,
            amount_rub=line.amount,
            flags=line.flags,
        )

    # ------------------------------------------------------------------ 1C
    def _build_1c_orders(self) -> None:
        for record in self.datasets[S_1C].orders:
            if record.is_duplicate:
                self._add_issue(
                    "duplicate_1c",
                    self.datasets[S_1C].filename,
                    record.source_id,
                    f"повтор order_id (строка {record.row_index})",
                    order=self._by_1c.get(record.source_id),
                )
                continue
            if not record.source_id:
                continue

            customer_id, customer_name = self._resolve_customer(record.customer_id, record.customer_name)
            order = self._new_order(
                customer_id=customer_id,
                customer_name=customer_name or record.customer_name or "Неизвестный заказчик",
                order_date=record.order_date or self.period_start,
                delivery_date=record.delivery_date,
                status=record.status or "new",
                total=record.total or Decimal("0"),
                currency=record.currency,
                confidence=Decimal("0.95"),
            )
            self._by_1c[record.source_id] = order
            self._by_any_key[record.source_id] = order
            self._link(order, S_1C, record.source_id, "exact_order_id", Decimal("1.00"), primary=True)

            prov_source = S_1C
            prov_id = record.source_id
            if self._is_suspect_customer(record.customer_id, customer_id):
                self._add_issue(
                    "missing_customer",
                    self.datasets[S_1C].filename,
                    order.canonical_order_id,
                    f"customer_id={record.customer_id or 'пусто'}, name={record.customer_name or 'пусто'}",
                    order=order,
                )
                if customer_id and record.customer_id != customer_id:
                    prov_source = "master_data"
                    prov_id = customer_id

            self._provenance(order, "customer_id", prov_source, prov_id, customer_id)
            self._provenance(order, "customer_name", S_1C, record.source_id, order.customer_name)
            self._provenance(order, "order_date", S_1C, record.source_id, order.order_date)
            if order.delivery_date:
                self._provenance(order, "delivery_date", S_1C, record.source_id, order.delivery_date)
            self._provenance(order, "status", S_1C, record.source_id, order.status)
            self._provenance(order, "total_rub", S_1C, record.source_id, order.total_rub)
            self._provenance(order, "currency", S_1C, record.source_id, order.currency)

            for line in self._lines_by_order.get(record.source_id, []):
                order.lines.append(self._line_from_record(line))
                self._line_issues(order, line)

            self._check_total(order, record.source_id)

    def _line_issues(self, order: CanonicalOrder, line: NormalizedLineRecord) -> None:
        source = self.datasets[S_1C_LINES].filename
        raw_sku = normalize_sku(line.sku_raw)
        if raw_sku not in self.master.product_by_sku:
            self._add_issue(
                "unknown_sku",
                source,
                order.canonical_order_id,
                f"SKU {line.sku_raw!r} отсутствует в мастер-данных",
                order=order,
                once_per_order=True,
            )
        if line.negative_qty:
            self._add_issue(
                "negative_qty",
                source,
                order.canonical_order_id,
                f"qty={line.qty} в строке {line.line_no}",
                order=order,
                once_per_order=True,
            )
        if line.unit and line.unit != "м":
            self._add_issue(
                "unit_mismatch",
                source,
                order.canonical_order_id,
                f"единица {line.unit!r} вместо 'м', qty={line.qty_raw}",
                order=order,
                once_per_order=True,
            )
        if "mixed_unit" in line.flags:
            self._add_issue(
                "mixed_unit",
                source,
                order.canonical_order_id,
                f"смешанная единица: {line.qty_raw!r}",
                order=order,
                once_per_order=True,
            )
        if "missing_conversion" in line.flags:
            self._add_issue(
                "missing_conversion",
                source,
                order.canonical_order_id,
                f"нет коэффициента для единицы {line.unit!r}",
                order=order,
                once_per_order=True,
            )

    def _check_total(self, order: CanonicalOrder, source_id: str) -> None:
        if not order.lines:
            return
        amounts = [line.amount_rub for line in order.lines]
        if any(amount is None for amount in amounts):
            return
        line_total = sum((amount for amount in amounts if amount is not None), Decimal("0"))
        if abs(order.total_rub - line_total) > TOTAL_MISMATCH_TOLERANCE:
            self._add_issue(
                "total_mismatch",
                self.datasets[S_1C].filename,
                order.canonical_order_id,
                f"шапка={order.total_rub}, строки={line_total}",
                order=order,
                once_per_order=True,
            )

    # ------------------------------------------------------------------ CRM
    def _apply_crm(self) -> None:
        for record in self.datasets[S_CRM].orders:
            if record.is_duplicate:
                self._add_issue(
                    "duplicate_crm",
                    self.datasets[S_CRM].filename,
                    record.source_id,
                    f"дубль сделки {record.duplicate_of}",
                    order=self._by_any_key.get(record.order_ref or ""),
                )
                continue

            target = self._by_any_key.get(record.order_ref or "")
            if target is not None:
                self._link(target, S_CRM, record.source_id, "exact_source_order", Decimal("1.00"))
                if crm_stage_conflicts(target.status, record.payload.get("stage")):
                    self._add_issue(
                        "status_conflict",
                        "1c/crm",
                        target.canonical_order_id,
                        f"1С={target.status}, CRM={record.payload.get('stage')}",
                        order=target,
                    )
                continue

            customer_id, customer_name = self._resolve_customer(record.customer_id, record.customer_name)
            order = self._new_order(
                customer_id=customer_id,
                customer_name=customer_name,
                order_date=self.period_start,
                delivery_date=self.period_start + timedelta(days=DEFAULT_LEAD_DAYS[S_CRM]),
                status=record.status or "new",
                total=record.total or Decimal("0"),
                currency="RUB",
                confidence=Decimal("0.60"),
            )
            self._by_any_key[record.source_id] = order
            self._link(order, S_CRM, record.source_id, "crm_only", Decimal("1.00"), primary=True)
            self._provenance(order, "customer_id", S_CRM, record.source_id, customer_id)
            self._provenance(order, "customer_name", S_CRM, record.source_id, order.customer_name)
            self._provenance(
                order, "order_date", "inferred", record.source_id, order.order_date, Decimal("0.60")
            )
            self._provenance(
                order, "delivery_date", "inferred", record.source_id, order.delivery_date, Decimal("0.60")
            )
            self._provenance(order, "status", S_CRM, record.source_id, order.status)
            self._provenance(order, "total_rub", S_CRM, record.source_id, order.total_rub)
            if self._is_suspect_customer(record.customer_id, customer_id):
                self._add_issue(
                    "missing_customer",
                    self.datasets[S_CRM].filename,
                    order.canonical_order_id,
                    f"customer_id={record.customer_id or 'пусто'}",
                    order=order,
                )

    # ------------------------------------------------------------------ email
    def _apply_email(self) -> None:
        self._rebuild_email_index()
        for record in self.datasets[S_EMAIL].orders:
            target = None
            method = None
            confidence = Decimal("1.00")
            if record.order_ref and record.order_ref in self._by_1c:
                target = self._by_1c[record.order_ref]
                method = "exact_order_ref"
            else:
                target, score, ambiguous = self._best_email_match(record)
                if target is not None and score >= FUZZY_EMAIL_THRESHOLD:
                    method = "fuzzy_customer_date"
                    confidence = score
                    if ambiguous:
                        self._add_issue(
                            "ambiguous_match",
                            self.datasets[S_EMAIL].filename,
                            record.source_id,
                            "несколько заказов совпали по клиенту и дате; выбран первый, нужен ручной разбор",
                            order=target,
                        )
                else:
                    target = None

            if target is not None:
                self._link(target, S_EMAIL, record.source_id, method or "fuzzy", confidence)
                continue

            customer_id, customer_name = self._resolve_customer(None, record.customer_name)
            order = self._new_order(
                customer_id=customer_id,
                customer_name=customer_name,
                order_date=self.period_start,
                delivery_date=self.period_start + timedelta(days=DEFAULT_LEAD_DAYS[S_EMAIL]),
                status="new",
                total=record.total or Decimal("0"),
                currency="RUB",
                confidence=Decimal("0.65"),
            )
            self._by_any_key[record.source_id] = order
            self._link(order, S_EMAIL, record.source_id, "email_only", Decimal("1.00"), primary=True)
            line = self._email_line(record)
            if line is not None:
                order.lines.append(line)
            self._provenance(order, "customer_id", S_EMAIL, record.source_id, customer_id)
            self._provenance(order, "customer_name", S_EMAIL, record.source_id, order.customer_name)
            self._provenance(
                order, "order_date", "inferred", record.source_id, order.order_date, Decimal("0.65")
            )
            self._provenance(
                order, "delivery_date", "inferred", record.source_id, order.delivery_date, Decimal("0.65")
            )
            self._provenance(order, "status", "rule", record.source_id, order.status, Decimal("0.65"))
            self._provenance(order, "total_rub", S_EMAIL, record.source_id, order.total_rub, Decimal("0.65"))
            self._add_issue(
                "email_only",
                self.datasets[S_EMAIL].filename,
                record.source_id,
                "заказ есть только в почте",
                order=order,
            )
            if self._is_suspect_customer(None, customer_id, require_raw_id=False):
                self._add_issue(
                    "missing_customer",
                    self.datasets[S_EMAIL].filename,
                    order.canonical_order_id,
                    f"клиент {record.customer_name!r} не найден",
                    order=order,
                )

    def _rebuild_email_index(self) -> None:
        self._email_index.clear()
        for order in self.orders:
            if not any(link.source_type == S_1C for link in order.links):
                continue
            key = (normalize_name(order.customer_name), order.order_date)
            self._email_index[key].append(order)

    def _best_email_match(self, record: NormalizedOrderRecord) -> tuple[CanonicalOrder | None, Decimal, bool]:
        if not record.order_date:
            return None, Decimal("0"), False
        customer = normalize_name(record.customer_name)
        if not customer:
            return None, Decimal("0"), False
        email_sku = normalize_sku(str(record.payload.get("sku") or ""))
        candidates: list[tuple[Decimal, CanonicalOrder]] = []
        for delta in (-1, 0, 1):
            day = record.order_date + timedelta(days=delta)
            for order in self._email_index.get((customer, day), []):
                score = Decimal("0.6") + (Decimal("0.3") if delta == 0 else Decimal("0.2"))
                if email_sku and any(line.sku == email_sku for line in order.lines):
                    score += Decimal("0.1")
                candidates.append((score, order))
        if not candidates:
            return None, Decimal("0"), False
        candidates.sort(key=lambda item: (-item[0], item[1].canonical_order_id))
        best_score, best = candidates[0]
        ambiguous = sum(1 for score, _order in candidates if score == best_score) > 1
        return best, best_score, ambiguous

    def _email_line(self, record: NormalizedOrderRecord) -> CanonicalLine | None:
        raw_sku = normalize_sku(str(record.payload.get("sku") or ""))
        if not raw_sku:
            return None
        quantity = None
        from app.normalization.units import normalize_quantity

        category = self.master.category_by_sku.get(raw_sku)
        quantity = normalize_quantity(
            record.payload.get("qty"), record.payload.get("unit"), category=category
        )
        price = None
        from app.normalization.money import parse_money

        price = parse_money(record.payload.get("price"))
        return CanonicalLine(
            source_type=S_EMAIL,
            source_id=record.source_id,
            line_no=1,
            sku=raw_sku,
            product_name=str(record.payload.get("comment") or ""),
            qty=quantity.qty,
            unit=quantity.unit,
            qty_m=quantity.qty_m,
            factor_to_m=quantity.factor_to_m,
            price_rub=price,
            amount_rub=None,
            flags=quantity.flags,
        )

    # ------------------------------------------------------------------ production
    def _apply_production(self) -> None:
        production_lines: dict[str, list[NormalizedLineRecord]] = defaultdict(list)
        for line in self.datasets[S_PRODUCTION].lines:
            production_lines[line.source_id].append(line)

        for record in self.datasets[S_PRODUCTION].orders:
            target = self._by_1c.get(record.order_ref or "")
            if target is not None:
                self._link(target, S_PRODUCTION, record.source_id, "exact_order_ref", Decimal("1.00"))
                continue

            line_records = production_lines.get(record.source_id, [])
            sku = line_records[0].sku if line_records else ""
            price = self.master.price_by_sku.get(sku)
            total = (price * 1000) if price is not None else Decimal("0")
            order = self._new_order(
                customer_id=None,
                customer_name="Неизвестный заказчик",
                order_date=self.period_start,
                delivery_date=record.delivery_date
                or (self.period_start + timedelta(days=DEFAULT_LEAD_DAYS[S_PRODUCTION])),
                status="in_production",
                total=total,
                currency="RUB",
                confidence=Decimal("0.55"),
            )
            self._by_any_key[record.source_id] = order
            self._link(
                order, S_PRODUCTION, record.source_id, "production_only", Decimal("1.00"), primary=True
            )
            if line_records:
                order.lines.append(self._line_from_record(line_records[0]))
            self._provenance(order, "customer_id", "none", record.source_id, None)
            self._provenance(order, "customer_name", "rule", record.source_id, order.customer_name)
            self._provenance(
                order, "order_date", "inferred", record.source_id, order.order_date, Decimal("0.55")
            )
            self._provenance(
                order, "delivery_date", S_PRODUCTION, record.source_id, order.delivery_date, Decimal("0.55")
            )
            self._provenance(order, "status", "rule", record.source_id, order.status, Decimal("0.55"))
            self._provenance(order, "total_rub", "rule", record.source_id, order.total_rub, Decimal("0.55"))
            self._add_issue(
                "orphan_production",
                self.datasets[S_PRODUCTION].filename,
                record.source_id,
                "заказ есть в производстве, но нет в 1С",
                order=order,
            )

    # ------------------------------------------------------------------ warehouse
    def _apply_warehouse(self) -> None:
        for record in self.datasets[S_WAREHOUSE].orders:
            if record.is_duplicate:
                self._add_issue(
                    "duplicate_warehouse",
                    self.datasets[S_WAREHOUSE].filename,
                    record.source_id,
                    f"повтор request_id {record.duplicate_of} (строка {record.row_index})",
                    order=self._by_1c.get(record.order_ref or ""),
                )
                continue
            target = self._by_1c.get(record.order_ref or "")
            if target is not None:
                self._link(target, S_WAREHOUSE, record.source_id, "exact_order_ref", Decimal("1.00"))
                continue
            self._add_issue(
                "orphan_warehouse",
                self.datasets[S_WAREHOUSE].filename,
                record.source_id,
                f"заявка ссылается на неизвестный заказ {record.order_ref!r}",
            )

    # ------------------------------------------------------------------ product-level
    def _conversion_issues(self) -> None:
        for sku, factors in self.master.conversion_conflicts.items():
            unique = sorted(set(factors))
            self._add_issue(
                "contradictory_conversion",
                "unit_coefficients_2026.xlsx",
                sku,
                "противоречивые коэффициенты: " + ", ".join(str(value) for value in unique),
            )

    def _coverage_issue(self) -> None:
        if self.profile == "reference" or self.erp_order_count is None:
            return
        missing = self.erp_order_count - len(self._by_1c)
        if missing > 0:
            self._add_issue(
                "coverage_gap",
                self.datasets[S_1C].filename,
                "aggregate",
                f"1С-выгрузка покрывает {len(self._by_1c)} из {self.erp_order_count} заказов ERP",
            )

    def _ambiguous_date_issues(self) -> None:
        if self.profile == "reference":
            return
        for dataset in self.datasets.values():
            for record in dataset.orders:
                if any(warning.startswith("ambiguous_date") for warning in record.warnings):
                    self._add_issue(
                        "ambiguous_date",
                        dataset.filename,
                        record.source_id,
                        ", ".join(record.warnings),
                    )
