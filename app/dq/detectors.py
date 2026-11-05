from __future__ import annotations

# Issue types produced by the core matching engine. The `reference` profile
# emits only these; `full` adds extended operational signals.
CORE_ISSUE_TYPES = {
    "duplicate_1c",
    "status_conflict",
    "unit_mismatch",
    "missing_customer",
    "unknown_sku",
    "total_mismatch",
    "negative_qty",
    "orphan_production",
    "email_only",
    "duplicate_crm",
    "duplicate_warehouse",
    "mixed_unit",
    "missing_conversion",
    "contradictory_conversion",
}

ISSUE_DESCRIPTIONS = {
    "duplicate_1c": "Повтор order_id в выгрузке 1С",
    "status_conflict": "Статус 1С не совпадает со стадией CRM",
    "unit_mismatch": "Строка заказа пришла не в базовой единице «м»",
    "missing_customer": "Пустой, заглушечный или неизвестный клиент",
    "unknown_sku": "SKU отсутствует в мастер-данных",
    "total_mismatch": "Сумма шапки не равна сумме строк",
    "negative_qty": "Отрицательное количество в строке",
    "orphan_production": "Производственное задание без заказа в 1С",
    "email_only": "Заказ существует только в почте",
    "duplicate_crm": "Дубль сделки CRM",
    "duplicate_warehouse": "Повтор request_id заявки на отгрузку",
    "mixed_unit": "Смешанная единица вида «2 барабана + 100 м»",
    "missing_conversion": "Нет коэффициента пересчёта в метры",
    "contradictory_conversion": "Противоречивые коэффициенты пересчёта",
    "orphan_warehouse": "Заявка склада ссылается на неизвестный заказ",
    "coverage_gap": "Выгрузка 1С покрывает не все заказы ERP",
    "ambiguous_date": "Неоднозначная дата DD/MM/YY",
    "ambiguous_match": "Несколько заказов одинаково подходят под запись источника",
}

SEVERITY = {
    "duplicate_1c": "low",
    "duplicate_crm": "low",
    "duplicate_warehouse": "low",
    "status_conflict": "high",
    "unit_mismatch": "medium",
    "missing_customer": "high",
    "unknown_sku": "medium",
    "total_mismatch": "high",
    "negative_qty": "high",
    "orphan_production": "medium",
    "orphan_warehouse": "medium",
    "email_only": "low",
    "mixed_unit": "high",
    "missing_conversion": "high",
    "contradictory_conversion": "high",
    "coverage_gap": "medium",
    "ambiguous_date": "low",
    "ambiguous_match": "medium",
}
