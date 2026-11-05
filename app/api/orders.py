from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth import UserContext, require_admin, require_analyst
from app.cache import cache
from app.db import get_db
from app.models import (
    AuditEvent,
    Customer,
    FieldProvenance,
    Issue,
    Order,
    OrderLine,
    OrderLink,
    OrderStatusHistory,
    Product,
)
from app.normalization.money import quantize_money
from app.normalization.statuses import CANONICAL_STATUSES
from app.normalization.units import normalize_quantity
from app.schemas import (
    IssueOut,
    OrderCreate,
    OrderDetail,
    OrderLineOut,
    OrderLinkOut,
    OrderListItem,
    OrderPatch,
    Page,
    ProvenanceOut,
    StatsOut,
    StatusChange,
    StatusHistoryOut,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

ALLOWED_TRANSITIONS = {
    "new": {"new", "confirmed", "closed"},
    "confirmed": {"confirmed", "in_production", "closed"},
    "in_production": {"in_production", "shipped", "closed"},
    "shipped": {"shipped", "closed"},
    "closed": {"closed"},
}


def _sources(db: Session, order_ids: list[int]) -> dict[int, list[str]]:
    if not order_ids:
        return {}
    result: dict[int, list[str]] = {}
    for link in db.scalars(select(OrderLink).where(OrderLink.order_id.in_(order_ids))):
        result.setdefault(link.order_id, []).append(link.source_type)
    return {key: sorted(set(value)) for key, value in result.items()}


def _item(order: Order, sources: list[str]) -> OrderListItem:
    return OrderListItem(
        canonical_order_id=order.canonical_order_id,
        customer_id=order.customer_id,
        customer_name=order.customer_name,
        order_date=order.order_date,
        delivery_date=order.delivery_date,
        status=order.status,
        total_rub=order.total_rub,
        currency=order.currency,
        match_confidence=order.match_confidence,
        issue_count=order.issue_count,
        is_manual=order.is_manual,
        sources=sources,
    )


def _cache_key(prefix: str, params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, default=str)
    return f"orderhub:{prefix}:{hashlib.sha1(raw.encode()).hexdigest()}"


@router.get("", response_model=Page[OrderListItem])
def list_orders(
    response: Response,
    status: str | None = None,
    customer_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    source_type: str | None = None,
    min_confidence: Decimal | None = Query(default=None, ge=0, le=1),
    has_issues: bool | None = None,
    q: str | None = None,
    sort: Literal[
        "canonical_order_id", "-canonical_order_id", "order_date", "-order_date"
    ] = "canonical_order_id",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[OrderListItem]:
    key = _cache_key(
        "orders",
        {
            "status": status,
            "customer_id": customer_id,
            "date_from": date_from,
            "date_to": date_to,
            "source_type": source_type,
            "min_confidence": min_confidence,
            "has_issues": has_issues,
            "q": q,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        },
    )
    cached = cache.get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return Page[OrderListItem](**cached)

    stmt = select(Order)
    if status:
        stmt = stmt.where(Order.status == status)
    if customer_id:
        stmt = stmt.where(Order.customer_id == customer_id)
    if date_from:
        stmt = stmt.where(Order.order_date >= date_from)
    if date_to:
        stmt = stmt.where(Order.order_date <= date_to)
    if source_type:
        stmt = stmt.where(Order.links.any(OrderLink.source_type == source_type))
    if min_confidence is not None:
        stmt = stmt.where(Order.match_confidence >= min_confidence)
    if has_issues is True:
        stmt = stmt.where(Order.issue_count > 0)
    elif has_issues is False:
        stmt = stmt.where(Order.issue_count == 0)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Order.canonical_order_id.ilike(pattern), Order.customer_name.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if sort.startswith("-"):
        stmt = stmt.order_by(getattr(Order, sort[1:]).desc())
    else:
        stmt = stmt.order_by(getattr(Order, sort).asc())
    orders = list(db.scalars(stmt.offset(offset).limit(limit)))
    sources = _sources(db, [order.id for order in orders])
    page = Page[OrderListItem](
        items=[_item(order, sources.get(order.id, [])) for order in orders],
        total=total,
        limit=limit,
        offset=offset,
    )
    cache.set(key, page.model_dump(mode="json"))
    response.headers["X-Cache"] = "MISS"
    return page


@router.post("", response_model=OrderDetail, status_code=201)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> OrderDetail:
    """Create a manual order that survives reconciliation.

    Generated orders come from the five sources and are rebuilt on every run.
    Manual orders use the ``CO-MAN-*`` namespace and an explicit ``manual`` link.
    """

    if payload.status not in CANONICAL_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status {payload.status!r}")

    customer_name = payload.customer_name
    if payload.customer_id:
        customer = db.get(Customer, payload.customer_id)
        if customer is None:
            raise HTTPException(status_code=422, detail=f"Unknown customer {payload.customer_id!r}")
        customer_name = customer.name or customer_name

    canonical_id = f"CO-MAN-{uuid4().hex[:8].upper()}"
    total = payload.total_rub
    computed = Decimal("0")
    all_amounts = True
    line_values: list[dict] = []
    for index, line in enumerate(payload.lines, start=1):
        product = db.get(Product, line.sku)
        normalized = normalize_quantity(line.qty, line.unit, category=product.category if product else None)
        amount = line.amount_rub
        if amount is None and line.price_rub is not None:
            amount = quantize_money(line.qty * line.price_rub)
        if amount is None:
            all_amounts = False
        else:
            computed += amount
        line_values.append(
            {
                "line_no": index,
                "sku": line.sku,
                "product_name": line.product_name or (product.name if product else ""),
                "qty": line.qty,
                "unit": normalized.unit or "м",
                "qty_m": normalized.qty_m,
                "price_rub": line.price_rub,
                "amount_rub": amount,
            }
        )

    if total is None:
        total = computed if all_amounts else Decimal("0")

    order = Order(
        canonical_order_id=canonical_id,
        customer_id=payload.customer_id,
        customer_name=customer_name,
        order_date=payload.order_date,
        delivery_date=payload.delivery_date,
        status=payload.status,
        total_rub=total,
        currency=payload.currency,
        match_confidence=Decimal("1.00"),
        issue_count=0,
        is_manual=True,
    )
    db.add(order)
    db.flush()

    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=None,
            to_status=order.status,
            actor=user.username,
            comment="manual order created",
        )
    )
    for values in line_values:
        db.add(OrderLine(order_id=order.id, source_type="manual", source_id=canonical_id, **values))
    db.add(
        OrderLink(
            order_id=order.id,
            source_type="manual",
            source_id=canonical_id,
            match_method="manual_create",
            confidence=Decimal("1.00"),
            is_primary=True,
        )
    )
    provenance = {
        "customer_id": payload.customer_id,
        "customer_name": customer_name,
        "order_date": payload.order_date.isoformat(),
        "delivery_date": payload.delivery_date.isoformat() if payload.delivery_date else None,
        "status": payload.status,
        "total_rub": str(total),
        "currency": payload.currency,
    }
    for field_name, value in provenance.items():
        db.add(
            FieldProvenance(
                order_id=order.id,
                field=field_name,
                source_type="manual",
                source_id=canonical_id,
                value={"value": value},
                confidence=Decimal("1.00"),
            )
        )
    db.add(
        AuditEvent(
            actor=user.username,
            action="order.create",
            entity="order",
            entity_id=canonical_id,
            payload={"customer_id": payload.customer_id, "lines": len(line_values)},
        )
    )
    db.commit()
    cache.invalidate()
    return _order_detail(db, canonical_id)[0]


@router.get("/export")
def export_orders(db: Session = Depends(get_db)) -> StreamingResponse:
    orders = list(db.scalars(select(Order).order_by(Order.canonical_order_id)))
    links: dict[int, dict[str, str]] = {}
    for link in db.scalars(select(OrderLink)):
        links.setdefault(link.order_id, {})[link.source_type] = link.source_id

    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            "canonical_order_id",
            "customer_id",
            "customer_name",
            "order_date",
            "delivery_date",
            "status",
            "total_rub",
            "source_1c",
            "source_crm",
            "source_email",
            "source_production",
            "source_warehouse",
            "match_confidence",
        ]
    )
    for order in orders:
        order_links = links.get(order.id, {})
        money = quantize_money(order.total_rub)
        writer.writerow(
            [
                order.canonical_order_id,
                order.customer_id or "",
                order.customer_name,
                order.order_date.isoformat(),
                order.delivery_date.isoformat() if order.delivery_date else "",
                order.status,
                str(money if money is not None else Decimal("0.00")),
                order_links.get("1c_orders", ""),
                order_links.get("crm_deals", ""),
                order_links.get("email_orders", ""),
                order_links.get("production_orders", ""),
                order_links.get("warehouse_requests", ""),
                str(order.match_confidence),
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="canonical_orders.csv"'},
    )


@router.get("/stats", response_model=StatsOut)
def order_stats(db: Session = Depends(get_db)) -> StatsOut:
    orders = db.scalar(select(func.count()).select_from(Order)) or 0
    issues = db.scalar(select(func.count()).select_from(Issue)) or 0
    open_issues = db.scalar(select(func.count()).select_from(Issue).where(Issue.status == "open")) or 0
    from app.models import ImportBatch

    imports = db.scalar(select(func.count()).select_from(ImportBatch)) or 0
    by_status = {
        str(status): count
        for status, count in db.execute(select(Order.status, func.count()).group_by(Order.status))
    }
    by_source = {
        str(source): count
        for source, count in db.execute(
            select(OrderLink.source_type, func.count(func.distinct(OrderLink.order_id))).group_by(
                OrderLink.source_type
            )
        )
    }
    by_issue_type = {
        str(issue_type): count
        for issue_type, count in db.execute(select(Issue.issue_type, func.count()).group_by(Issue.issue_type))
    }
    return StatsOut(
        orders=orders,
        issues=issues,
        open_issues=open_issues,
        imports=imports,
        by_status=by_status,
        by_source=by_source,
        by_issue_type=by_issue_type,
    )


def _order_detail(db: Session, canonical_order_id: str) -> tuple[OrderDetail, bool]:
    key = _cache_key("order", {"id": canonical_order_id})
    cached = cache.get(key)
    if cached is not None:
        return OrderDetail(**cached), True

    order = db.scalar(
        select(Order)
        .options(
            selectinload(Order.lines),
            selectinload(Order.links),
            selectinload(Order.provenance),
            selectinload(Order.issues),
            selectinload(Order.status_history),
        )
        .where(Order.canonical_order_id == canonical_order_id)
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    provenance = [
        ProvenanceOut(
            field=item.field,
            source_type=item.source_type,
            source_id=item.source_id,
            value=item.value.get("value")
            if isinstance(item.value, dict) and "value" in item.value
            else item.value,
            confidence=item.confidence,
        )
        for item in sorted(order.provenance, key=lambda row: row.field)
    ]
    detail = OrderDetail(
        **_item(order, sorted({link.source_type for link in order.links})).model_dump(),
        lines=[OrderLineOut.model_validate(line) for line in order.lines],
        links=[OrderLinkOut.model_validate(link) for link in order.links],
        provenance=provenance,
        issues=[
            IssueOut.model_validate(issue)
            for issue in sorted(order.issues, key=lambda row: (row.severity, row.issue_type))
        ],
        status_history=[
            StatusHistoryOut.model_validate(item)
            for item in sorted(order.status_history, key=lambda row: row.id)
        ],
    )
    cache.set(key, detail.model_dump(mode="json"))
    return detail, False


@router.get("/{canonical_order_id}", response_model=OrderDetail)
def get_order(
    response: Response,
    canonical_order_id: str,
    db: Session = Depends(get_db),
) -> OrderDetail:
    detail, cache_hit = _order_detail(db, canonical_order_id)
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return detail


@router.patch("/{canonical_order_id}", response_model=OrderDetail)
def patch_order(
    canonical_order_id: str,
    payload: OrderPatch,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_analyst),
) -> OrderDetail:
    order = db.scalar(select(Order).where(Order.canonical_order_id == canonical_order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status is not None and payload.status not in CANONICAL_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status {payload.status!r}")
    if payload.customer_id is not None and db.get(Customer, payload.customer_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown customer {payload.customer_id!r}")
    previous_status = order.status
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is not None:
            setattr(order, field, value)
    if order.status != previous_status:
        db.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=previous_status,
                to_status=order.status,
                actor=user.username,
                comment="status changed via PATCH",
            )
        )
    db.add(
        AuditEvent(
            actor=user.username,
            action="order.patch",
            entity="order",
            entity_id=canonical_order_id,
            payload={key: str(value) for key, value in changes.items()},
        )
    )
    db.commit()
    cache.invalidate()
    return _order_detail(db, canonical_order_id)[0]


@router.delete("/{canonical_order_id}", status_code=204)
def delete_order(
    canonical_order_id: str,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_admin),
) -> Response:
    order = db.scalar(select(Order).where(Order.canonical_order_id == canonical_order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not order.is_manual:
        raise HTTPException(
            status_code=409,
            detail="Only manually created orders can be deleted; generated orders are rebuilt by reconciliation",
        )
    db.add(
        AuditEvent(
            actor=user.username,
            action="order.delete",
            entity="order",
            entity_id=canonical_order_id,
            payload={"customer_id": order.customer_id, "total_rub": str(order.total_rub)},
        )
    )
    db.delete(order)
    db.commit()
    cache.invalidate()
    return Response(status_code=204)


@router.post("/{canonical_order_id}/status", response_model=OrderDetail)
def change_status(
    canonical_order_id: str,
    payload: StatusChange,
    db: Session = Depends(get_db),
    user: UserContext = Depends(require_analyst),
) -> OrderDetail:
    order = db.scalar(select(Order).where(Order.canonical_order_id == canonical_order_id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status not in CANONICAL_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unknown status {payload.status!r}")
    allowed = ALLOWED_TRANSITIONS.get(order.status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Transition {order.status!r} -> {payload.status!r} is not allowed",
        )
    previous = order.status
    order.status = payload.status
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=previous,
            to_status=payload.status,
            actor=user.username,
            comment=payload.comment,
        )
    )
    db.add(
        AuditEvent(
            actor=user.username,
            action="order.status",
            entity="order",
            entity_id=canonical_order_id,
            payload={"from": previous, "to": payload.status, "comment": payload.comment},
        )
    )
    db.commit()
    cache.invalidate()
    return _order_detail(db, canonical_order_id)[0]
