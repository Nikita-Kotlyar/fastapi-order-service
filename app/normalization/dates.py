from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

EXCEL_EPOCH = date(1899, 12, 30)

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DMY_DOT_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$")
_DMY_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$")
_YMD_SLASH_RE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_SERIAL_RE = re.compile(r"^\d{5}(?:\.0+)?$")


@dataclass(frozen=True)
class ParsedDate:
    value: date | None
    raw: str
    fmt: str | None = None
    ambiguous: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.value is not None


def _from_serial(value: int | float) -> date:
    return EXCEL_EPOCH + timedelta(days=int(value))


def _build(year: int, month: int, day: int) -> date:
    if year < 100:
        year += 2000
    return date(year, month, day)


def parse_date(value: object, *, day_first: bool = True) -> ParsedDate:
    """Parse the date formats found in the source extracts into a single ISO date.

    Supported: date/datetime objects, ISO, DD.MM.YYYY, DD/MM/YY, YYYY/MM/DD,
    Excel serial numbers (1899-12-30 epoch). Slash dates where both parts are
    <= 12 are marked ambiguous but still parsed as day-first by default.
    """

    if value is None or (isinstance(value, str) and not value.strip()):
        return ParsedDate(None, "", error="empty")

    if isinstance(value, datetime):
        return ParsedDate(value.date(), value.isoformat(), "datetime")
    if isinstance(value, date):
        return ParsedDate(value, value.isoformat(), "date")

    raw = str(value).strip()
    try:
        if isinstance(value, (int, float)) or _SERIAL_RE.fullmatch(raw):
            serial = int(float(raw))
            if 20000 <= serial <= 90000:
                return ParsedDate(_from_serial(serial), raw, "excel_serial")
            return ParsedDate(None, raw, error="serial_out_of_range")

        match = _ISO_RE.match(raw)
        if match:
            year, month, day = match.groups()
            return ParsedDate(_build(int(year), int(month), int(day)), raw, "iso")

        match = _DMY_DOT_RE.fullmatch(raw)
        if match:
            day, month, year = match.groups()
            return ParsedDate(_build(int(year), int(month), int(day)), raw, "dd.mm.yyyy")

        match = _YMD_SLASH_RE.fullmatch(raw)
        if match:
            year, month, day = match.groups()
            return ParsedDate(_build(int(year), int(month), int(day)), raw, "yyyy/mm/dd")

        match = _DMY_SLASH_RE.fullmatch(raw)
        if match:
            first, second, year = (int(part) for part in match.groups())
            ambiguous = first <= 12 and second <= 12 and first != second
            if day_first:
                day, month = first, second
            else:
                month, day = first, second
            return ParsedDate(_build(year, month, day), raw, "dd/mm/yy", ambiguous=ambiguous)
    except ValueError as exc:
        return ParsedDate(None, raw, error=str(exc))

    return ParsedDate(None, raw, error="unsupported_format")
