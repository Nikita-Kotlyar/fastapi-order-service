from __future__ import annotations

CANONICAL_STATUSES = ("new", "confirmed", "in_production", "shipped", "closed")

STATUS_RANK = {
    "new": 0,
    "confirmed": 1,
    "in_production": 2,
    "shipped": 3,
    "closed": 4,
}

_STATUS_SYNONYMS = {
    "новый": "new",
    "новая": "new",
    "new": "new",
    "создан": "new",
    "подтвержден": "confirmed",
    "подтверждён": "confirmed",
    "confirmed": "confirmed",
    "в работе": "in_production",
    "в производстве": "in_production",
    "in_production": "in_production",
    "in progress": "in_production",
    "in_progress": "in_production",
    "отгружен": "shipped",
    "отгружено": "shipped",
    "shipped": "shipped",
    "закрыт": "closed",
    "закрыто": "closed",
    "closed": "closed",
}

CRM_STAGE_TO_STATUS = {
    "new": "new",
    "negotiation": "new",
    "won": "confirmed",
    "lost": "closed",
}

# Which canonical statuses are compatible with a CRM stage. A mismatch is a
# business conflict, not a formatting error, so it is reported instead of silently fixed.
_CRM_STAGE_COMPATIBLE = {
    "new": {"new"},
    "negotiation": {"new", "confirmed", "in_production"},
    "won": {"shipped", "closed"},
    "lost": {"closed"},
}

PRODUCTION_STATUS_TO_CANONICAL = {
    "plan": "confirmed",
    "planned": "confirmed",
    "in_progress": "in_production",
    "in progress": "in_production",
    "done": "shipped",
    "completed": "shipped",
}

WAREHOUSE_STATUS_TO_CANONICAL = {
    "new": "confirmed",
    "planned": "confirmed",
    "shipped": "shipped",
    "done": "shipped",
}

_SOURCE_PRIORITY = {"1c": 4, "production": 3, "warehouse": 2, "crm": 1, "email": 0}


def normalize_status(value: str | None) -> str | None:
    if value is None:
        return None
    key = " ".join(value.strip().lower().replace("_", " ").split())
    return _STATUS_SYNONYMS.get(key) or _STATUS_SYNONYMS.get(key.replace(" ", "_"))


def crm_stage_conflicts(canonical_status: str | None, crm_stage: str | None) -> bool:
    if not canonical_status or not crm_stage:
        return False
    stage = crm_stage.strip().lower()
    compatible = _CRM_STAGE_COMPATIBLE.get(stage)
    if compatible is None:
        return False
    return canonical_status not in compatible


def resolve_status(candidates: list[tuple[str, str]]) -> tuple[str, str]:
    """Pick the status from the most trusted source.

    ``candidates`` is a list of ``(source_type, status)``. Returns
    ``(status, source_type)``. 1C wins over production, production over
    warehouse, warehouse over CRM, CRM over email.
    """

    valid = [(source, status) for source, status in candidates if status in STATUS_RANK]
    if not valid:
        return "new", "fallback"
    valid.sort(key=lambda item: _SOURCE_PRIORITY.get(item[0], -1), reverse=True)
    return valid[0][1], valid[0][0]
