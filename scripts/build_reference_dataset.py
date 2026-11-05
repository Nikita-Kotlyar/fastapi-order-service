"""Generate a deterministic reference dataset for integration tests.

The dataset mirrors the file formats and defect patterns of the production
reconciliation pipeline, so the service can be exercised in a reproducible
environment without external systems.

Usage:
    python scripts/build_reference_dataset.py
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data" / "reference"
EXCEL_EPOCH = date(1899, 12, 30)


def serial(value: date) -> int:
    return (value - EXCEL_EPOCH).days


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    customers = [
        [
            "CUST-001",
            "ООО «Альфа»",
            "5000000001",
            "500000001",
            "Орёл",
            "Иванов И.И.",
            "alpha@example.ru",
            "+7 4862 000-01-01",
            "Петров П.П.",
            "опт",
            "1000000",
            "30",
            "",
        ],
        [
            "CUST-002",
            "АО «Бета»",
            "5000000002",
            "500000002",
            "Курск",
            "Сидоров С.С.",
            "beta@example.ru",
            "+7 4862 000-01-02",
            "Петров П.П.",
            "опт",
            "2000000",
            "45",
            "",
        ],
        [
            "CUST-003",
            "ООО «Гамма»",
            "5000000003",
            "500000003",
            "Белгород",
            "Кузнецов К.К.",
            "gamma@example.ru",
            "+7 4862 000-01-03",
            "Смирнов С.С.",
            "розница",
            "500000",
            "14",
            "",
        ],
    ]
    products = [
        [
            "CBL-VVG-LS-3x1,5-S01",
            "Кабель ВВГнг(А)-LS 3x1,5 (партия 01)",
            "27.32.13.190",
            "ГОСТ 31996-2012",
            "м",
            "100.00",
            "ВВГнг(А)-LS",
            "0.66",
            "3",
            "1.5",
            "ПВХ пониженной горючести",
            "80.05",
            "500",
        ],
        [
            "CBL-KVVG-3x1,5-S01",
            "Кабель КВВГ 3x1,5 (партия 01)",
            "27.32.13.190",
            "ГОСТ 31996-2012",
            "м",
            "80.00",
            "КВВГ",
            "0.66",
            "3",
            "1.5",
            "ПВХ",
            "70.00",
            "500",
        ],
        [
            "CBL-VBSHV-LS-3x2,5-S01",
            "Кабель ВБШвнг(А)-LS 3x2,5 (партия 01)",
            "27.32.13.190",
            "ГОСТ 31996-2012",
            "м",
            "150.00",
            "ВБШвнг(А)-LS",
            "0.66",
            "3",
            "2.5",
            "ПВХ пониженной горючести",
            "120.00",
            "500",
        ],
        [
            "CBL-PPG-HF-3x1,5-S01",
            "Кабель ППГнг(А)-HF 3x1,5 (партия 01)",
            "27.32.13.190",
            "ГОСТ 31996-2012",
            "м",
            "120.00",
            "ППГнг(А)-HF",
            "0.66",
            "3",
            "1.5",
            "безгалогенный",
            "90.00",
            "500",
        ],
        [
            "CBL-KPS-FRLS-3x1,5-S01",
            "Кабель КПСЭнг(А)-FRLS 3x1,5 (партия 01)",
            "27.32.13.190",
            "ГОСТ 31996-2012",
            "м",
            "90.00",
            "КПСЭнг(А)-FRLS",
            "0.66",
            "3",
            "1.5",
            "FRLS",
            "75.00",
            "500",
        ],
    ]

    # ERP: 20 orders, only 10 are exported to 1C, which creates a coverage gap.
    base = [
        ("ORD-1001", "2026-01-10", "2026-01-20", "CUST-001", "ООО «Альфа»", "confirmed", "100000.00"),
        ("ORD-1002", "2026-02-01", "2026-02-15", "CUST-002", "АО «Бета»", "in_production", "80000.00"),
        ("ORD-1003", "2026-03-05", "2026-03-10", "CUST-003", "ООО «Гамма»", "shipped", "120000.00"),
        ("ORD-1004", "2026-04-01", "2026-04-10", "CUST-001", "ООО «Альфа»", "closed", "60000.00"),
        ("ORD-1005", "2026-05-01", "2026-05-15", "CUST-002", "АО «Бета»", "confirmed", "90000.00"),
        ("ORD-1006", "2026-06-01", "2026-06-20", "CUST-003", "ООО «Гамма»", "in_production", "75000.00"),
        ("ORD-1007", "2026-07-01", "2026-07-15", "CUST-001", "ООО «Альфа»", "confirmed", "110000.00"),
        ("ORD-1008", "2026-08-01", "2026-08-10", "CUST-002", "АО «Бета»", "shipped", "95000.00"),
        ("ORD-1009", "2026-09-01", "2026-09-10", "CUST-003", "ООО «Гамма»", "closed", "70000.00"),
        ("ORD-1010", "2026-10-01", "2026-10-15", "CUST-001", "ООО «Альфа»", "confirmed", "85000.00"),
    ]
    erp_rows = []
    for oid, od, dd, cid, cname, status, total in base:
        erp_rows.append([oid, od, dd, cid, cname, status, "normal", "Петров П.П.", total, "RUB", ""])
    for index in range(11, 21):
        oid = f"ORD-{1000 + index}"
        erp_rows.append(
            [
                oid,
                "2026-10-03",
                "2026-10-20",
                "CUST-003",
                "ООО «Гамма»",
                "new",
                "low",
                "Смирнов С.С.",
                "40000.00",
                "RUB",
                "",
            ]
        )
    write_csv(
        REFERENCE / "data/erp/orders_2026.csv",
        [
            "order_id",
            "order_date",
            "delivery_date",
            "customer_id",
            "customer_name",
            "status",
            "priority",
            "manager",
            "total_rub",
            "currency",
            "comment",
        ],
        erp_rows,
    )

    # 1C headers: mixed date formats, comma decimals, blank/placeholder customers,
    # a duplicate, a header total mismatch and a status that conflicts with CRM.
    one_c = [
        [
            "ORD-1001",
            "2026-01-10",
            "2026-01-20",
            "CUST-001",
            "ООО «Альфа»",
            "confirmed",
            "100000.0",
            "RUB",
            "",
        ],
        [
            "ORD-1002",
            "01.02.2026",
            "15.02.2026",
            "CUST-002",
            "АО «Бета»",
            "in_production",
            "80000,0",
            "RUB",
            "",
        ],
        ["ORD-1003", "05/03/26", "10/03/26", "CUST-003", "ООО «Гамма»", "shipped", "120000.0", "RUB", ""],
        [
            "ORD-1004",
            str(serial(date(2026, 4, 1))),
            "2026-04-10",
            "CUST-001",
            "ООО «Альфа»",
            "closed",
            "60000.0",
            "RUB",
            "",
        ],
        ["ORD-1005", "2026-05-01", "2026-05-15", "", "АО «Бета»", "confirmed", "90000.0", "RUB", ""],
        [
            "ORD-1006",
            "2026-06-01",
            "2026-06-20",
            "CUST-999",
            "ООО «Гамма»",
            "in_production",
            "75000.0",
            "RUB",
            "",
        ],
        [
            "ORD-1007",
            "2026-07-01",
            "2026-07-15",
            "CUST-001",
            "ООО «Альфа»",
            "confirmed",
            "115500.0",
            "RUB",
            "",
        ],
        [
            "ORD-1008",
            "2026-08-01",
            "2026-08-10",
            "CUST-002",
            "АО «Бета»",
            "in_production",
            "95000.0",
            "RUB",
            "",
        ],
        ["ORD-1009", "2026-09-01", "2026-09-10", "CUST-003", "ООО «Гамма»", "closed", "70000.0", "RUB", ""],
        [
            "ORD-1010",
            "2026-10-01",
            "2026-10-15",
            "CUST-001",
            "ООО «Альфа»",
            "confirmed",
            "85000.0",
            "RUB",
            "",
        ],
        [
            "ORD-1003",
            "05.03.2026",
            "10.03.2026",
            "CUST-003",
            "ООО «Гамма»",
            "confirmed",
            "116400,0",
            "RUB",
            "дубль выгрузки",
        ],
    ]
    write_csv(
        REFERENCE / "data/integration/1c_orders_export.csv",
        [
            "order_id",
            "order_date",
            "delivery_date",
            "customer_id",
            "customer_name",
            "status",
            "total_rub",
            "currency",
            "comment",
        ],
        one_c,
    )

    # Lines: km, pieces, mixed units, drum, pallet place, package, unknown SKU,
    # negative quantity and a line total that makes ORD-1007 mismatch.
    lines = [
        [
            "ORD-1001",
            "CBL-VVG-LS-3x1,5-S01",
            "Кабель ВВГнг(А)-LS 3x1,5 (партия 01)",
            "1000",
            "м",
            "100.00",
            "100000.0",
        ],
        [
            "ORD-1002",
            "CBL-VVG-LS-3x1,5-S01",
            "Кабель ВВГнг(А)-LS 3x1,5 (партия 01)",
            "80",
            "км",
            "1000.00",
            "80000.0",
        ],
        [
            "ORD-1003",
            "CBL-VBSHV-LS-3x2,5-S01",
            "Кабель ВБШвнг(А)-LS 3x2,5 (партия 01)",
            "800",
            "м",
            "150.00",
            "120000.0",
        ],
        [
            "ORD-1004",
            "CBL-VVG-LS-3x1,5-S01",
            "Кабель ВВГнг(А)-LS 3x1,5 (партия 01)",
            "-600",
            "м",
            "100.00",
            "60000.0",
        ],
        [
            "ORD-1005",
            "CBL-PPG-HF-3x1,5-S01",
            "Кабель ППГнг(А)-HF 3x1,5 (партия 01)",
            "750",
            "шт",
            "120.00",
            "90000.0",
        ],
        [
            "ORD-1006",
            "CBL-KVVG-3x1,5-S01",
            "Кабель КВВГ 3x1,5 (партия 01)",
            "2 барабана + 150 м",
            "смеш.",
            "80.00",
            "75000.0",
        ],
        [
            "ORD-1007",
            "CBL-VVG-LS-3x1,5-S01",
            "Кабель ВВГнг(А)-LS 3x1,5 (партия 01)",
            "1100",
            "м",
            "100.00",
            "110000.0",
        ],
        [
            "ORD-1008",
            "CBL-PPG-HF-3x1,5-S01",
            "Кабель ППГнг(А)-HF 3x1,5 (партия 01)",
            "2",
            "барабан",
            "47500.00",
            "95000.0",
        ],
        [
            "ORD-1009",
            "CBL-UNKNOWN-001",
            "Кабель КПСЭнг(А)-FRLS 3x1,5 (партия 01)",
            "70",
            "палетоместо",
            "1000.00",
            "70000.0",
        ],
        [
            "ORD-1010",
            "CBL-KPS-FRLS-3x1,5-S01",
            "Кабель КПСЭнг(А)-FRLS 3x1,5 (партия 01)",
            "17",
            "упаковка",
            "5000.00",
            "85000.0",
        ],
    ]
    write_csv(
        REFERENCE / "data/integration/1c_order_lines_export.csv",
        ["order_id", "sku", "product_name", "qty", "unit", "price_rub", "amount_rub"],
        lines,
    )

    crm = [
        {
            "deal_id": "DEAL-1001",
            "customer_id": "CUST-001",
            "customer_name": "ООО «Альфа»",
            "amount": 102000.0,
            "stage": "won",
            "created_at": "2026-01-10",
            "source_order": "ORD-1001",
        },
        {
            "deal_id": "DEAL-1002",
            "customer_id": "CUST-002",
            "customer_name": "АО «Бета»",
            "amount": 81600.0,
            "stage": "negotiation",
            "created_at": "01.02.2026",
            "source_order": "ORD-1002",
        },
        {
            "deal_id": "DEAL-1003",
            "customer_id": "CUST-003",
            "customer_name": "ООО «Гамма»",
            "amount": 122400.0,
            "stage": "won",
            "created_at": "2026-03-05",
            "source_order": "ORD-1003",
        },
        {
            "deal_id": "DEAL-1004",
            "customer_id": "CUST-001",
            "customer_name": "ООО «Альфа»",
            "amount": 61200.0,
            "stage": "won",
            "created_at": "2026-04-01",
            "source_order": "ORD-1004",
        },
        {
            "deal_id": "DEAL-1005",
            "customer_id": "CUST-002",
            "customer_name": "АО «Бета»",
            "amount": 91800.0,
            "stage": "negotiation",
            "created_at": "2026-05-01",
            "source_order": "ORD-1005",
        },
        {
            "deal_id": "DEAL-1006",
            "customer_id": "CUST-003",
            "customer_name": "ООО «Гамма»",
            "amount": 76500.0,
            "stage": "negotiation",
            "created_at": "2026-06-01",
            "source_order": "ORD-1006",
        },
        {
            "deal_id": "DEAL-1007",
            "customer_id": "CUST-001",
            "customer_name": "ООО «Альфа»",
            "amount": 112200.0,
            "stage": "negotiation",
            "created_at": "2026-07-01",
            "source_order": "ORD-1007",
        },
        {
            "deal_id": "DEAL-2001",
            "customer_id": "CUST-002",
            "customer_name": "АО «Бета»",
            "amount": 45000.0,
            "stage": "new",
            "created_at": "2026-11-01",
            "source_order": "",
        },
        {
            "deal_id": "DEAL-2002",
            "customer_id": "CUST-003",
            "customer_name": "ООО «Гамма»",
            "amount": 55000.0,
            "stage": "negotiation",
            "created_at": "2026-11-02",
            "source_order": "",
        },
        {
            "deal_id": "DEAL-8001",
            "customer_id": "CUST-002",
            "customer_name": "АО «Бета»",
            "amount": 45000.0,
            "stage": "negotiation",
            "created_at": "2026-11-01",
            "source_order": "",
        },
    ]
    write_json(REFERENCE / "data/integration/crm_deals_export.json", crm)

    email = Workbook()
    ws = email.active
    ws.title = "Заказы из почты"
    ws.append(["email_id", "order_ref", "customer", "order_date", "sku", "qty", "unit", "price", "comment"])
    ws.append(
        [
            "EMAIL-1001",
            "№ ORD-1001",
            "ООО «Альфа»",
            "2026-01-10",
            "CBL-VVG-LS-3x1,5-S01",
            1000,
            "м",
            100.0,
            "",
        ]
    )
    ws.append(["EMAIL-1002", "б/н", "АО «Бета»", "01.02.2026", "CBL-KVVG-3x1,5-S01", 500, "м", 80.0, ""])
    ws.append(
        ["EMAIL-1003", "№ ORD-1003", "ООО «Гамма»", "05/03/26", "CBL-VBSHV-LS-3x2,5-S01", 800, "м", 150.0, ""]
    )
    ws.append(
        [
            "EMAIL-9001",
            "б/н",
            "ООО «Гамма»",
            "2026-11-02",
            "CBL-VBSHV-LS-3x2,5-S01",
            1000,
            "м",
            150.0,
            "заявка из письма",
        ]
    )
    ws.append(
        [
            "EMAIL-9002",
            "б/н",
            "ООО «Альфа»",
            "2026-11-03",
            "CBL-PPG-HF-3x1,5-S01",
            500,
            "м",
            120.0,
            "заявка из письма",
        ]
    )
    email.save(REFERENCE / "data/integration/sales_orders_from_email.xlsx")

    production = [
        ["ORD-1001", "CBL-VVG-LS-3x1,5-S01", "1000", "м", "Цех 1", "done", "2026-01-18"],
        ["ORD-1002", "CBL-VVG-LS-3x1,5-S01", "80", "км", "Цех 2", "in_progress", "2026-02-12"],
        ["ORD-1003", "CBL-VBSHV-LS-3x2,5-S01", "800", "м", "Цех 3", "done", "2026-03-08"],
        ["ORD-1004", "CBL-VVG-LS-3x1,5-S01", "600", "м", "Цех 1", "done", "2026-04-08"],
        ["ORD-1005", "CBL-PPG-HF-3x1,5-S01", "750", "м", "Цех 2", "in_progress", "2026-05-12"],
        ["PRD-2001", "CBL-KPS-FRLS-3x1,5-S01", "1000", "м", "Цех 3", "plan", "2026-11-30"],
        ["PRD-2002", "CBL-VVG-LS-3x1,5-S01", "500", "м", "Цех 1", "plan", "2026-12-05"],
    ]
    write_csv(
        REFERENCE / "data/integration/production_orders_export.csv",
        ["order_ref", "sku", "qty", "unit", "workshop", "status", "planned_end"],
        production,
    )

    warehouse = [
        ["WR-1001", "ORD-1001", "CBL-VVG-LS-3x1,5-S01", "1000", "м", "2026-01-19", "new"],
        ["WR-1002", "ORD-1002", "CBL-VVG-LS-3x1,5-S01", "80", "км", "2026-02-14", "new"],
        ["WR-1003", "ORD-1003", "CBL-VBSHV-LS-3x2,5-S01", "800", "м", "2026-03-09", "new"],
        ["WR-1004", "ORD-1004", "CBL-VVG-LS-3x1,5-S01", "600", "м", "2026-04-09", "new"],
        ["WR-1005", "ORD-1005", "CBL-PPG-HF-3x1,5-S01", "750", "м", "2026-05-14", "new"],
        ["WR-9001", "UNKNOWN", "CBL-VVG-LS-3x1,5-S01", "100", "м", "2026-11-20", "new"],
        ["WR-1001", "ORD-1001", "CBL-VVG-LS-3x1,5-S01", "100", "м", "2026-11-21", "new"],
    ]
    write_csv(
        REFERENCE / "data/integration/warehouse_shipment_requests.csv",
        ["request_id", "order_ref", "sku", "qty", "unit", "ship_date", "status"],
        warehouse,
    )

    write_csv(
        REFERENCE / "data/integration/unit_notes.csv",
        ["note_id", "source", "sku", "text"],
        [
            ["NOTE-001", "warehouse", "CBL-VVG-LS-3x1,5-S01", "1 барабан ВВГ = 500 м, для КВВГ — 300 м."],
            ["NOTE-002", "procurement", "", "Палетоместо: 20 упаковок; в накладной поставщика — 24."],
        ],
    )
    write_csv(
        REFERENCE / "data/integration/warehouse_weighing.csv",
        [
            "weighing_id",
            "sku",
            "declared_qty",
            "declared_unit",
            "actual_weight_kg",
            "unit_weight_kg",
            "delta_pct",
        ],
        [
            ["WEIGH-001", "CBL-VVG-LS-3x1,5-S01", "1000", "м", "80050.0", "80.05", "0.0"],
            ["WEIGH-002", "CBL-KVVG-3x1,5-S01", "500", "м", "35000.0", "70.00", "0.0"],
        ],
    )

    price = Workbook()
    (REFERENCE / "data/procurement/price_lists").mkdir(parents=True, exist_ok=True)
    ws = price.active
    ws.title = "Прайс"
    ws.append(["sku", "unit", "factor_to_m", "price_per_unit", "note"])
    for row in products:
        sku, _name, _okpd, _std, _unit, price_rub, category, *_rest = row
        drum = 300 if category == "КВВГ" else 500
        for unit, factor, note in [
            ("барабан", drum, "по регламенту"),
            ("упаковка", 50, ""),
            ("палетоместо", 1000, "20 упаковок"),
            ("км", 1000, ""),
            ("шт", None, "коэффициент не задан"),
        ]:
            ws.append([sku, unit, factor, round(float(price_rub) * factor, 2) if factor else None, note])
    price.save(REFERENCE / "data/procurement/price_lists/unit_coefficients_2026.xlsx")

    write_csv(
        REFERENCE / "config/customers.csv",
        [
            "customer_id",
            "name",
            "inn",
            "kpp",
            "city",
            "contact",
            "email",
            "phone",
            "manager",
            "segment",
            "credit_limit_rub",
            "payment_days",
            "duplicate_group",
        ],
        customers,
    )
    write_csv(
        REFERENCE / "config/products.csv",
        [
            "sku",
            "name",
            "okpd2",
            "standard",
            "unit",
            "price_rub",
            "category",
            "voltage_kv",
            "cores",
            "section_mm2",
            "insulation",
            "weight_kg_km",
            "min_stock_m",
        ],
        products,
    )

    (REFERENCE / "data/integration/README.txt").write_text(
        "Reference dataset for integration tests and reproducible environments.\n"
        "10 orders in 1C, 2 CRM-only, 2 email-only, 2 production-only.\n",
        encoding="utf-8",
    )
    print(f"Reference dataset written to {REFERENCE}")


if __name__ == "__main__":
    main()
