from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    roles: Mapped[str] = mapped_column(String(128), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def role_list(self) -> list[str]:
        return [role.strip() for role in self.roles.split(",") if role.strip()]


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("run_id", "source_type", "filename", name="uq_batch_run_source_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("reconciliation_runs.id", ondelete="SET NULL"))
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceRecord(Base):
    """Immutable raw record kept for audit and reprocessing."""

    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_type", "record_key", name="uq_source_record_key"),
        Index("ix_source_records_lookup", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(String(128), index=True)
    record_key: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="accepted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    inn: Mapped[str | None] = mapped_column(String(32))
    kpp: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(128))
    segment: Mapped[str | None] = mapped_column(String(64))
    duplicate_group: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CustomerAlias(Base):
    __tablename__ = "customer_aliases"
    __table_args__ = (UniqueConstraint("source", "alias", name="uq_customer_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(512), index=True)
    normalized_alias: Mapped[str] = mapped_column(String(512), index=True)
    source: Mapped[str] = mapped_column(String(64))


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(512), index=True)
    normalized_name: Mapped[str] = mapped_column(String(512), index=True)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    unit: Mapped[str] = mapped_column(String(32), default="м")
    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    weight_kg_km: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    min_stock_m: Mapped[Decimal | None] = mapped_column(Numeric(18, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (UniqueConstraint("source", "alias", name="uq_product_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(512), index=True)
    normalized_alias: Mapped[str] = mapped_column(String(512), index=True)
    source: Mapped[str] = mapped_column(String(64))


class UnitConversion(Base):
    __tablename__ = "unit_conversions"
    __table_args__ = (
        UniqueConstraint("sku", "unit", "source", name="uq_unit_conversion"),
        Index("ix_unit_conversions_lookup", "sku", "unit"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(128), index=True)
    unit: Mapped[str] = mapped_column(String(32), index=True)
    factor_to_m: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    source: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.0"))
    note: Mapped[str | None] = mapped_column(String(512))


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_order_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(512), default="")
    order_date: Mapped[date] = mapped_column(Date, index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    total_rub: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.50"))
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    lines: Mapped[list[OrderLine]] = relationship(
        back_populates="order", cascade="all, delete-orphan", passive_deletes=True
    )
    links: Mapped[list[OrderLink]] = relationship(
        back_populates="order", cascade="all, delete-orphan", passive_deletes=True
    )
    provenance: Mapped[list[FieldProvenance]] = relationship(
        back_populates="order", cascade="all, delete-orphan", passive_deletes=True
    )
    issues: Mapped[list[Issue]] = relationship(back_populates="order", passive_deletes=True)
    status_history: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="order", cascade="all, delete-orphan", passive_deletes=True
    )


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (Index("ix_order_lines_order", "order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(128))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    sku: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(512), default="")
    qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str] = mapped_column(String(32))
    qty_m: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount_rub: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    order: Mapped[Order] = relationship(back_populates="lines")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    __table_args__ = (Index("ix_order_status_history_order", "order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128), default="system")
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="status_history")


class OrderLink(Base):
    __tablename__ = "order_links"
    __table_args__ = (
        UniqueConstraint("order_id", "source_type", "source_id", name="uq_order_link"),
        Index("ix_order_links_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(128))
    match_method: Mapped[str] = mapped_column(String(64), default="exact")
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="links")


class FieldProvenance(Base):
    __tablename__ = "field_provenance"
    __table_args__ = (UniqueConstraint("order_id", "field", name="uq_provenance_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(128))
    value: Mapped[dict[str, Any]] = mapped_column(JSON)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))

    order: Mapped[Order] = relationship(back_populates="provenance")


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("issue_key", name="uq_issue_key"),
        Index("ix_issues_status_type", "status", "issue_type"),
        Index("ix_issues_order", "order_canonical_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_key: Mapped[str] = mapped_column(String(64))
    issue_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    source: Mapped[str] = mapped_column(String(128))
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    order_canonical_id: Mapped[str | None] = mapped_column(String(64))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order | None] = relationship(back_populates="issues")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile: Mapped[str] = mapped_column(String(32), default="full")
    status: Mapped[str] = mapped_column(String(32), default="running")
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batches: Mapped[list[ImportBatch]] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
