from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.normalization.money import parse_decimal

_MIXED_RE = re.compile(
    r"(?P<qty>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>барабан\w*|палетомест\w*|паллетомест\w*|упаков\w*|рулон\w*|км|м)\b",
    re.IGNORECASE,
)

_UNIT_SYNONYMS = {
    "м": "м",
    "м.": "м",
    "метр": "м",
    "метра": "м",
    "метров": "м",
    "км": "км",
    "км.": "км",
    "километр": "км",
    "километров": "км",
    "рулон": "рулон",
    "рулона": "рулон",
    "рулонов": "рулон",
    "барабан": "барабан",
    "барабана": "барабан",
    "барабанов": "барабан",
    "палетоместо": "палетоместо",
    "палетомест": "палетоместо",
    "паллетоместо": "палетоместо",
    "паллетомест": "палетоместо",
    "упаковка": "упаковка",
    "упаковку": "упаковка",
    "упаковок": "упаковка",
    "упак": "упаковка",
    "шт": "шт",
    "шт.": "шт",
    "штука": "шт",
    "штук": "шт",
    "смеш": "смеш.",
    "смеш.": "смеш.",
    "смешанная": "смеш.",
}

_BASE_UNIT = "м"


@dataclass(frozen=True)
class UnitConversionRule:
    unit: str
    factor_to_m: Decimal | None
    source: str
    confidence: Decimal
    note: str = ""


@dataclass(frozen=True)
class NormalizedQuantity:
    qty: Decimal | None
    unit: str
    qty_m: Decimal | None
    factor_to_m: Decimal | None
    confidence: Decimal = Decimal("1.0")
    components: tuple[tuple[Decimal, str], ...] = field(default_factory=tuple)
    flags: tuple[str, ...] = field(default_factory=tuple)


def normalize_unit(value: str | None) -> str:
    if not value:
        return ""
    key = value.strip().lower().replace("ё", "е")
    return _UNIT_SYNONYMS.get(key, key)


def default_conversion_rules(category: str | None = None) -> list[UnitConversionRule]:
    """Conversion knowledge available without the price list.

    Rolls are a convention (100 m) and are deliberately marked with low
    confidence. KVvG drums have two contradictory sources: the general
    regulation says 500 m, the supplier price list says 300 m.
    """

    rules = [
        UnitConversionRule("м", Decimal("1"), "base", Decimal("1.00")),
        UnitConversionRule("км", Decimal("1000"), "regulation", Decimal("1.00")),
        UnitConversionRule("упаковка", Decimal("50"), "regulation", Decimal("0.90")),
        UnitConversionRule("палетоместо", Decimal("1000"), "regulation", Decimal("0.80")),
        UnitConversionRule("барабан", Decimal("500"), "regulation", Decimal("0.90")),
        UnitConversionRule("рулон", Decimal("100"), "convention", Decimal("0.60"), "длина рулона не задана"),
        UnitConversionRule("шт", None, "none", Decimal("0.00"), "коэффициент не задан"),
    ]
    if category and category.upper() == "КВВГ":
        rules.append(
            UnitConversionRule(
                "барабан",
                Decimal("300"),
                "price_list",
                Decimal("0.70"),
                "прайс поставщика: 300 м; регламент: 500 м",
            )
        )
    return rules


def _select_rule(rules: list[UnitConversionRule], unit: str) -> UnitConversionRule | None:
    candidates = [rule for rule in rules if rule.unit == unit]
    if not candidates:
        return None
    with_factor = [rule for rule in candidates if rule.factor_to_m is not None]
    if not with_factor:
        return candidates[0]
    # Price list is the most current product-specific source; otherwise the
    # highest-confidence rule wins.
    with_factor.sort(key=lambda rule: (rule.source == "price_list", rule.confidence), reverse=True)
    return with_factor[0]


def _has_conflicting_factors(rules: list[UnitConversionRule], unit: str) -> bool:
    factors = {rule.factor_to_m for rule in rules if rule.unit == unit and rule.factor_to_m is not None}
    return len(factors) > 1


def parse_mixed_quantity(value: str) -> tuple[tuple[Decimal, str], ...]:
    components: list[tuple[Decimal, str]] = []
    for match in _MIXED_RE.finditer(value):
        qty = parse_decimal(match.group("qty"))
        unit = normalize_unit(match.group("unit"))
        if qty is not None:
            components.append((qty, unit))
    return tuple(components)


def normalize_quantity(
    raw_qty: object,
    raw_unit: str | None,
    *,
    category: str | None = None,
    rules: list[UnitConversionRule] | None = None,
) -> NormalizedQuantity:
    rules = rules or default_conversion_rules(category)
    unit = normalize_unit(raw_unit)
    flags: list[str] = []

    # Mixed rows look like "2 барабана + 100 м" and arrive with unit "смеш.".
    components: tuple[tuple[Decimal, str], ...] = ()
    if unit == "смеш." or (isinstance(raw_qty, str) and _MIXED_RE.search(raw_qty)):
        components = parse_mixed_quantity(str(raw_qty))
        flags.append("mixed_unit")
        if not components:
            return NormalizedQuantity(None, "смеш.", None, None, Decimal("0.0"), (), tuple(flags))
        total = Decimal("0")
        min_confidence = Decimal("1.0")
        for qty, component_unit in components:
            rule = _select_rule(rules, component_unit)
            if rule is None or rule.factor_to_m is None:
                flags.append("missing_conversion")
                min_confidence = Decimal("0.0")
                continue
            total += qty * rule.factor_to_m
            min_confidence = min(min_confidence, rule.confidence)
        if _has_conflicting_factors(rules, "барабан"):
            flags.append("contradictory_conversion")
        return NormalizedQuantity(None, "смеш.", total, None, min_confidence, components, tuple(flags))

    qty = parse_decimal(raw_qty)
    if qty is None:
        return NormalizedQuantity(None, unit, None, None, Decimal("0.0"), (), ("invalid_qty",))

    rule = _select_rule(rules, unit)
    if rule is None:
        flags.append("missing_conversion")
        return NormalizedQuantity(qty, unit, None, None, Decimal("0.0"), (), tuple(flags))

    if rule.factor_to_m is None:
        flags.append("missing_conversion")
        return NormalizedQuantity(qty, unit, None, None, rule.confidence, (), tuple(flags))

    if unit != _BASE_UNIT:
        flags.append("non_base_unit")
    if _has_conflicting_factors(rules, unit):
        flags.append("contradictory_conversion")

    return NormalizedQuantity(
        qty=qty,
        unit=unit,
        qty_m=qty * rule.factor_to_m,
        factor_to_m=rule.factor_to_m,
        confidence=rule.confidence,
        flags=tuple(flags),
    )
