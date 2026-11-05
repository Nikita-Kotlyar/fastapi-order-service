from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_QUANT = Decimal("0.01")


def parse_decimal(value: object) -> Decimal | None:
    """Parse numbers written by humans: ``1 234,56``, ``1234.56``, ``(12,00)``."""

    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    raw = str(value).strip()
    if not raw:
        return None

    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]

    raw = (
        raw.replace(" ", "")
        .replace(" ", "")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
        .replace("RUB", "")
        .strip()
    )
    if not raw:
        return None

    if "," in raw and "." in raw:
        # 1.234,56 -> 1234.56 ; 1,234.56 -> 1234.56
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")

    try:
        result = Decimal(raw)
    except InvalidOperation:
        return None
    return -result if negative else result


def quantize_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def parse_money(value: object) -> Decimal | None:
    return quantize_money(parse_decimal(value))
