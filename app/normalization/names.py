from __future__ import annotations

import re

_QUOTES = "«»\"'`"
_LEGAL_FORMS = (
    "ооо",
    "оао",
    "зао",
    "пао",
    "ао",
    "ип",
    "нко",
    "гк",
    "фгуп",
    "муп",
)
_SPACES_RE = re.compile(r"\s+")
_PARTY_SUFFIX_RE = re.compile(r"\(\s*\d{1,3}\s*\)\s*$")


def normalize_name(value: str | None) -> str:
    """Normalise a counterparty name for blocking and exact-after-cleaning matches."""

    if not value:
        return ""
    text = value.strip().lower().replace("ё", "е")
    for quote in _QUOTES:
        text = text.replace(quote, "")
    text = _PARTY_SUFFIX_RE.sub("", text)
    text = _SPACES_RE.sub(" ", text).strip(" .,")
    for form in _LEGAL_FORMS:
        if text.startswith(form + " "):
            text = text[len(form) + 1 :]
            break
    return _SPACES_RE.sub(" ", text).strip(" .,")


def normalize_sku(value: str | None) -> str:
    """SKU is a case-sensitive business key: strip whitespace, keep the rest."""

    if not value:
        return ""
    return _SPACES_RE.sub("", value.strip())
