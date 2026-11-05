from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ingestion.readers import read_csv_dicts, read_xlsx_dicts
from app.models import Customer, CustomerAlias, Product, ProductAlias, UnitConversion
from app.normalization.money import parse_decimal, parse_money
from app.normalization.names import normalize_name, normalize_sku
from app.normalization.units import default_conversion_rules, normalize_unit


@dataclass
class MasterData:
    customer_by_id: dict[str, dict] = field(default_factory=dict)
    customer_by_name: dict[str, str] = field(default_factory=dict)
    product_by_sku: dict[str, dict] = field(default_factory=dict)
    sku_by_name: dict[str, str] = field(default_factory=dict)
    category_by_sku: dict[str, str] = field(default_factory=dict)
    price_by_sku: dict[str, Decimal] = field(default_factory=dict)
    conversion_conflicts: dict[str, list[Decimal]] = field(default_factory=dict)


def _upsert_customer(session: Session, row: dict[str, str]) -> Customer:
    customer_id = (row.get("customer_id") or "").strip()
    customer = session.get(Customer, customer_id)
    values = {
        "name": (row.get("name") or "").strip(),
        "normalized_name": normalize_name(row.get("name")),
        "inn": (row.get("inn") or "").strip() or None,
        "kpp": (row.get("kpp") or "").strip() or None,
        "city": (row.get("city") or "").strip() or None,
        "segment": (row.get("segment") or "").strip() or None,
        "duplicate_group": (row.get("duplicate_group") or "").strip() or None,
    }
    if customer is None:
        customer = Customer(customer_id=customer_id, **values)
        session.add(customer)
    else:
        for key, value in values.items():
            setattr(customer, key, value)
    return customer


def _upsert_product(session: Session, row: dict[str, str]) -> Product:
    sku = normalize_sku(row.get("sku"))
    product = session.get(Product, sku)
    values = {
        "name": (row.get("name") or "").strip(),
        "normalized_name": normalize_name(row.get("name")),
        "category": (row.get("category") or "").strip() or None,
        "unit": normalize_unit(row.get("unit")) or "м",
        "price_rub": parse_money(row.get("price_rub")),
        "weight_kg_km": parse_decimal(row.get("weight_kg_km")),
        "min_stock_m": parse_decimal(row.get("min_stock_m")),
    }
    if product is None:
        product = Product(sku=sku, **values)
        session.add(product)
    else:
        for key, value in values.items():
            setattr(product, key, value)
    return product


def seed_master_data(session: Session, source_dir: Path) -> MasterData:
    customers_path = source_dir / "config" / "customers.csv"
    products_path = source_dir / "config" / "products.csv"
    price_list_path = source_dir / "data" / "procurement" / "price_lists" / "unit_coefficients_2026.xlsx"

    session.execute(delete(CustomerAlias))
    session.execute(delete(ProductAlias))
    session.execute(delete(UnitConversion))

    data = MasterData()
    for row in read_csv_dicts(customers_path, ";"):
        customer = _upsert_customer(session, row)
        data.customer_by_id[customer.customer_id] = {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "normalized_name": customer.normalized_name,
        }
        if customer.normalized_name:
            data.customer_by_name[customer.normalized_name] = customer.customer_id
            session.add(
                CustomerAlias(
                    customer_id=customer.customer_id,
                    alias=customer.name,
                    normalized_alias=customer.normalized_name,
                    source="master_data",
                )
            )
        session.add(
            CustomerAlias(
                customer_id=customer.customer_id,
                alias=customer.customer_id,
                normalized_alias=customer.customer_id.lower(),
                source="master_data_id",
            )
        )

    conversions: list[dict] = []
    for row in read_csv_dicts(products_path, ";"):
        product = _upsert_product(session, row)
        data.product_by_sku[product.sku] = {
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "price_rub": product.price_rub,
            "unit": product.unit,
        }
        if product.normalized_name:
            data.sku_by_name[product.normalized_name] = product.sku
            session.add(
                ProductAlias(
                    sku=product.sku,
                    alias=product.name,
                    normalized_alias=product.normalized_name,
                    source="master_data",
                )
            )
        if product.category:
            data.category_by_sku[product.sku] = product.category
        if product.price_rub is not None:
            data.price_by_sku[product.sku] = product.price_rub
        for rule in default_conversion_rules(product.category):
            conversions.append(
                {
                    "sku": product.sku,
                    "unit": rule.unit,
                    "factor_to_m": rule.factor_to_m,
                    "source": rule.source,
                    "confidence": rule.confidence,
                    "note": rule.note,
                }
            )

    if price_list_path.exists():
        for row in read_xlsx_dicts(price_list_path, "Прайс"):
            sku = normalize_sku(str(row.get("sku") or ""))
            if not sku:
                continue
            conversions.append(
                {
                    "sku": sku,
                    "unit": normalize_unit(str(row.get("unit") or "")),
                    "factor_to_m": parse_decimal(row.get("factor_to_m")),
                    "source": "price_list",
                    "confidence": Decimal("0.90"),
                    "note": str(row.get("note") or ""),
                }
            )

    seen: set[tuple[str, str, str]] = set()
    for item in conversions:
        key = (item["sku"], item["unit"], item["source"])
        if key in seen:
            continue
        seen.add(key)
        session.add(UnitConversion(**item))

    factors: dict[tuple[str, str], set[Decimal]] = {}
    for item in conversions:
        if item["factor_to_m"] is None:
            continue
        factors.setdefault((item["sku"], item["unit"]), set()).add(item["factor_to_m"])
    for (sku, _unit), values in factors.items():
        if len(values) > 1:
            data.conversion_conflicts.setdefault(sku, []).extend(sorted(values))

    session.flush()
    return data


def load_master_data(session: Session) -> MasterData:
    data = MasterData()
    for customer in session.scalars(select(Customer)):
        data.customer_by_id[customer.customer_id] = {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "normalized_name": customer.normalized_name,
        }
        data.customer_by_name[customer.normalized_name] = customer.customer_id
    for product in session.scalars(select(Product)):
        data.product_by_sku[product.sku] = {
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "price_rub": product.price_rub,
            "unit": product.unit,
        }
        data.sku_by_name[product.normalized_name] = product.sku
        if product.category:
            data.category_by_sku[product.sku] = product.category
        if product.price_rub is not None:
            data.price_by_sku[product.sku] = product.price_rub
    factors: dict[tuple[str, str], set[Decimal]] = {}
    for conversion in session.scalars(select(UnitConversion)):
        if conversion.factor_to_m is None:
            continue
        factors.setdefault((conversion.sku or "", conversion.unit), set()).add(conversion.factor_to_m)
    for (sku, _unit), values in factors.items():
        if len(values) > 1:
            data.conversion_conflicts.setdefault(sku, []).extend(sorted(values))
    return data
