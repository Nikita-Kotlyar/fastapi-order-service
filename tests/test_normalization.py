from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.normalization.dates import parse_date
from app.normalization.money import parse_decimal, parse_money
from app.normalization.names import normalize_name, normalize_sku
from app.normalization.statuses import crm_stage_conflicts, normalize_status, resolve_status
from app.normalization.units import normalize_quantity, normalize_unit, parse_mixed_quantity


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-21", date(2026, 1, 21)),
        ("21.01.2026", date(2026, 1, 21)),
        ("25/07/26", date(2026, 7, 25)),
        ("46248", date(2026, 8, 14)),
        (46248, date(2026, 8, 14)),
        ("04/09/26", date(2026, 9, 4)),
    ],
)
def test_parse_date_formats(raw: object, expected: date) -> None:
    parsed = parse_date(raw)
    assert parsed.value == expected
    assert parsed.ok


def test_parse_date_flags_ambiguous_slash_date() -> None:
    parsed = parse_date("04/09/26")
    assert parsed.value == date(2026, 9, 4)
    assert parsed.ambiguous is True


def test_parse_date_rejects_garbage() -> None:
    parsed = parse_date("not a date")
    assert parsed.value is None
    assert parsed.error == "unsupported_format"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 234,56", Decimal("1234.56")),
        ("2585720.4", Decimal("2585720.4")),
        ("(12,00)", Decimal("-12.00")),
        ("1.234,56 ₽", Decimal("1234.56")),
    ],
)
def test_parse_decimal(raw: str, expected: Decimal) -> None:
    assert parse_decimal(raw) == expected


def test_parse_money_quantizes() -> None:
    assert parse_money("10,005") == Decimal("10.01")


def test_normalize_names() -> None:
    assert normalize_name("АО «Энергосеть» (03)") == "энергосеть"
    assert normalize_sku(" CBL-KVVG-2x1,5-S01 ") == "CBL-KVVG-2x1,5-S01"


def test_normalize_unit_synonyms() -> None:
    assert normalize_unit("Барабанов") == "барабан"
    assert normalize_unit("паллетомест") == "палетоместо"
    assert normalize_unit("смеш") == "смеш."


def test_quantity_km_to_m() -> None:
    result = normalize_quantity("8", "км")
    assert result.qty == Decimal("8")
    assert result.qty_m == Decimal("8000")
    assert "non_base_unit" in result.flags


def test_quantity_mixed_expression_vvg() -> None:
    result = normalize_quantity("2 барабана + 100 м", "смеш.", category="ВВГ")
    assert result.qty_m == Decimal("1100")
    assert "mixed_unit" in result.flags


def test_quantity_mixed_expression_kvvg_uses_price_list() -> None:
    result = normalize_quantity("2 барабана + 100 м", "смеш.", category="КВВГ")
    assert result.qty_m == Decimal("700")
    assert "contradictory_conversion" in result.flags


def test_quantity_pieces_without_conversion() -> None:
    result = normalize_quantity("5", "шт")
    assert result.qty_m is None
    assert "missing_conversion" in result.flags


def test_parse_mixed_quantity_components() -> None:
    assert parse_mixed_quantity("2 барабана + 150 м") == (
        (Decimal("2"), "барабан"),
        (Decimal("150"), "м"),
    )


def test_status_normalization_and_conflicts() -> None:
    assert normalize_status("in_progress") == "in_production"
    assert normalize_status("Отгружен") == "shipped"
    assert crm_stage_conflicts("shipped", "won") is False
    assert crm_stage_conflicts("confirmed", "won") is True
    assert crm_stage_conflicts("in_production", "negotiation") is False


def test_status_priority() -> None:
    status, source = resolve_status([("crm", "new"), ("1c", "shipped"), ("production", "in_production")])
    assert status == "shipped"
    assert source == "1c"
