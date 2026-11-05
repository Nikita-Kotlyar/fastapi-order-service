from __future__ import annotations

from decimal import Decimal

FUZZY_EMAIL_THRESHOLD = Decimal("0.85")

# Fallback delivery SLA for records that have no delivery date anywhere.
# Used only for single-source records and always marked as inferred.
DEFAULT_LEAD_DAYS = {
    "crm_deals": 19,
    "email_orders": 24,
    "production_orders": 29,
}

TOTAL_MISMATCH_TOLERANCE = Decimal("0.01")
