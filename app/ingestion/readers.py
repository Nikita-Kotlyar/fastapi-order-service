from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def read_csv_dicts(path: Path, delimiter: str | None = None) -> list[dict[str, str]]:
    text = _decode(path.read_bytes())
    if delimiter is None:
        probe = text[:8192]
        delimiter = max((";", ",", "\t"), key=lambda char: probe.count(char))
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [{(key or "").strip(): (value or "").strip() for key, value in row.items()} for row in reader]


def read_json(path: Path) -> Any:
    return json.loads(_decode(path.read_bytes()))


def read_xlsx_dicts(path: Path, sheet_name: str | None = None) -> list[dict[str, Any]]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    worksheet = workbook[sheet_name] if sheet_name else workbook.worksheets[0]
    rows = list(worksheet.iter_rows(values_only=True))
    workbook.close()
    if not rows:
        return []
    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    result: list[dict[str, Any]] = []
    for row in rows[1:]:
        if all(value is None or str(value).strip() == "" for value in row):
            continue
        result.append({headers[index]: value for index, value in enumerate(row) if index < len(headers)})
    return result
