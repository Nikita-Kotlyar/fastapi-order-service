from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    roles: list[str]
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=6, max_length=128)
    roles: list[str] = Field(default_factory=lambda: ["viewer"])


class UserPatch(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=128)
    roles: list[str] | None = None
    is_active: bool | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    name: str
    inn: str | None = None
    city: str | None = None
    segment: str | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    category: str | None = None
    unit: str
    price_rub: Decimal | None = None


class UnitConversionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str | None
    unit: str
    factor_to_m: Decimal | None
    source: str
    confidence: Decimal
    note: str | None = None


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: str
    line_no: int
    sku: str
    product_name: str
    qty: Decimal | None
    unit: str
    qty_m: Decimal | None
    price_rub: Decimal | None
    amount_rub: Decimal | None


class OrderLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_type: str
    source_id: str
    match_method: str
    confidence: Decimal
    is_primary: bool


class ProvenanceOut(BaseModel):
    field: str
    source_type: str
    source_id: str
    value: Any
    confidence: Decimal


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_key: str
    issue_type: str
    severity: str
    source: str
    source_id: str
    order_canonical_id: str | None = None
    details: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class OrderListItem(BaseModel):
    canonical_order_id: str
    customer_id: str | None
    customer_name: str
    order_date: date
    delivery_date: date | None
    status: str
    total_rub: Decimal
    currency: str
    match_confidence: Decimal
    issue_count: int
    is_manual: bool = False
    sources: list[str] = Field(default_factory=list)


class OrderLineCreate(BaseModel):
    sku: str = Field(min_length=1)
    product_name: str = ""
    qty: Decimal = Field(gt=0)
    unit: str = "м"
    price_rub: Decimal | None = Field(default=None, ge=0)
    amount_rub: Decimal | None = Field(default=None, ge=0)


class OrderCreate(BaseModel):
    customer_id: str | None = None
    customer_name: str = Field(min_length=1)
    order_date: date
    delivery_date: date | None = None
    status: str = "new"
    total_rub: Decimal | None = Field(default=None, ge=0)
    currency: str = "RUB"
    lines: list[OrderLineCreate] = Field(default_factory=list)


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: str | None
    to_status: str
    actor: str
    comment: str | None
    created_at: datetime


class OrderDetail(OrderListItem):
    lines: list[OrderLineOut]
    links: list[OrderLinkOut]
    provenance: list[ProvenanceOut]
    issues: list[IssueOut]
    status_history: list[StatusHistoryOut] = Field(default_factory=list)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class OrderPatch(BaseModel):
    customer_id: str | None = None
    customer_name: str | None = None
    order_date: date | None = None
    delivery_date: date | None = None
    status: str | None = None
    total_rub: Decimal | None = Field(default=None, ge=0)


class StatusChange(BaseModel):
    status: str
    comment: str | None = None


class IssueAction(BaseModel):
    note: str | None = None


class ReconciliationRequest(BaseModel):
    profile: str = Field(default="full", pattern="^(reference|full)$")
    dry_run: bool = False
    run_date: date | None = None


class ReconciliationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile: str
    status: str
    stats: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    source_type: str
    filename: str
    sha256: str
    row_count: int
    status: str
    created_at: datetime


class SourceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: str | None
    record_key: str
    status: str
    created_at: datetime


class StatsOut(BaseModel):
    orders: int
    issues: int
    open_issues: int
    imports: int
    by_status: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    by_issue_type: dict[str, int] = Field(default_factory=dict)
