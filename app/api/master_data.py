from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Customer, Product, UnitConversion
from app.schemas import CustomerOut, Page, ProductOut, UnitConversionOut

router = APIRouter(prefix="/api/v1", tags=["master-data"])


@router.get("/customers", response_model=Page[CustomerOut])
def list_customers(
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[CustomerOut]:
    stmt = select(Customer)
    if q:
        stmt = stmt.where(Customer.name.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(Customer.customer_id).offset(offset).limit(limit)))
    return Page[CustomerOut](
        items=[CustomerOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products", response_model=Page[ProductOut])
def list_products(
    q: str | None = None,
    category: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[ProductOut]:
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q.strip()}%"))
    if category:
        stmt = stmt.where(Product.category == category)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.order_by(Product.sku).offset(offset).limit(limit)))
    return Page[ProductOut](
        items=[ProductOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unit-conversions", response_model=Page[UnitConversionOut])
def list_unit_conversions(
    sku: str | None = None,
    unit: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> Page[UnitConversionOut]:
    stmt = select(UnitConversion)
    if sku:
        stmt = stmt.where(UnitConversion.sku == sku)
    if unit:
        stmt = stmt.where(UnitConversion.unit == unit)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(stmt.order_by(UnitConversion.sku, UnitConversion.unit).offset(offset).limit(limit))
    )
    return Page[UnitConversionOut](
        items=[UnitConversionOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
