# Архитектура Order Hub

## Назначение

`fastapi-order-service` — industrial order hub для производственного предприятия
кабельной отрасли. Название компании и данные обезличены по требованиям NDA.
Сервис собирает заказ из пяти корпоративных систем, нормализует поля, строит
golden record, хранит провенанс и ведёт реестр расхождений.

## Контекст

```mermaid
flowchart LR
    subgraph Legacy["Legacy-системы"]
        C1["1С: шапки и строки"]
        C2["CRM: сделки"]
        C3["Почта: XLSX"]
        C4["Производство: CSV"]
        C5["Склад: CSV"]
    end

    subgraph Hub["Order Hub"]
        ING["Ingest + SHA-256"]
        NORM["Normalize"]
        MATCH["Entity resolution"]
        GOLD["Golden record"]
        DQ["DQ registry"]
        API["FastAPI /api/v1"]
    end

    C1 --> ING
    C2 --> ING
    C3 --> ING
    C4 --> ING
    C5 --> ING
    ING --> NORM --> MATCH --> GOLD --> DQ --> API
    API --> UI["Swagger / BI / agents"]
```

## Слои

| Слой | Пакет | Ответственность |
|---|---|---|
| HTTP | `app/api` | маршруты, пагинация, роли, OpenAPI |
| Auth | `app/auth.py`, `app/security.py` | JWT access/refresh, PBKDF2, RBAC |
| Services | `app/services` | запуск сверки, persistence, audit |
| Ingestion | `app/ingestion` | чтение CSV/JSON/XLSX, нормализация источников, мастер-данные |
| Matching | `app/matching` | entity resolution, golden record, провенанс |
| Normalization | `app/normalization` | даты, Decimal, единицы, статусы, имена, SKU |
| DQ | `app/dq` | типы проблем, severity, описания |
| Data | `app/models.py`, `alembic` | SQLAlchemy-модели и миграции |
| Infra | `Dockerfile`, `docker-compose.yml`, `.github` | PostgreSQL, Redis, CI, CD |

## Модель данных

```mermaid
erDiagram
    USERS {
        int id PK
        string username UK
        string password_hash
        string roles
        bool is_active
    }
    IMPORT_BATCHES {
        int id PK
        string source_type
        string sha256
        int row_count
    }
    SOURCE_RECORDS {
        int id PK
        int batch_id FK
        string source_type
        string source_id
        json payload
    }
    ORDERS {
        int id PK
        string canonical_order_id UK
        string customer_id
        date order_date
        date delivery_date
        string status
        numeric total_rub
        bool is_manual
    }
    ORDER_LINES {
        int id PK
        int order_id FK
        string sku
        numeric qty
        string unit
        numeric qty_m
    }
    ORDER_LINKS {
        int id PK
        int order_id FK
        string source_type
        string source_id
    }
    FIELD_PROVENANCE {
        int id PK
        int order_id FK
        string field
        string source_type
    }
    ORDER_STATUS_HISTORY {
        int id PK
        int order_id FK
        string from_status
        string to_status
        string actor
    }
    ISSUES {
        int id PK
        string issue_key UK
        string issue_type
        string source_id
        string status
    }
    RECONCILIATION_RUNS {
        int id PK
        string profile
        string status
        json stats
    }
    AUDIT_EVENTS {
        int id PK
        string actor
        string action
        string entity
    }

    IMPORT_BATCHES ||--o{ SOURCE_RECORDS : contains
    ORDERS ||--o{ ORDER_LINES : has
    ORDERS ||--o{ ORDER_LINKS : has
    ORDERS ||--o{ FIELD_PROVENANCE : has
    ORDERS ||--o{ ORDER_STATUS_HISTORY : has
    ORDERS ||--o{ ISSUES : can_have
    RECONCILIATION_RUNS ||--o{ IMPORT_BATCHES : produces
```

## Поток сверки

```mermaid
sequenceDiagram
    actor Analyst
    participant API as FastAPI
    participant Svc as ReconciliationService
    participant Files as Sources (CSV/JSON/XLSX)
    participant Matcher as OrderMatcher
    participant DB as PostgreSQL

    Analyst->>API: POST /api/v1/reconciliation/runs
    API->>Svc: run(profile, dry_run, run_date)
    Svc->>Files: read five sources + master data
    Svc->>Matcher: normalize, match, golden record, DQ
    Matcher-->>Svc: 580 orders + issues + provenance
    Svc->>DB: rebuild generated orders, upsert issue keys
    Svc->>DB: import_batches + source_records + audit_event
    Svc-->>API: stats
    API-->>Analyst: run_id + counts
```

## Матчинг

1. **Точные ключи:** `order_id`, `source_order`, `order_ref`, `deal_id`, `email_id`, `request_id`.
2. **Fuzzy для почты без ссылки:** нормализованный клиент + дата ±1 день + SKU, порог `0.85`.
3. **Карантин:** `UNKNOWN`, `PRD-*`, неразрешимые ссылки не создают golden record.
4. **Приоритет полей:** 1С → CRM → почта → производство → склад.
5. **Деньги:** только `Decimal`, CRM-сумма не перезаписывает 1С.
6. **Повторный запуск:** canonical ID детерминированы, issue keys стабильны,
   ручные заказы `CO-MAN-*` и статусы `resolved/ignored` сохраняются.

## Авторизация

```mermaid
sequenceDiagram
    participant Client
    participant Auth as /auth/token
    participant DB as users
    participant API as protected endpoint

    Client->>Auth: username + password (OAuth2 form)
    Auth->>DB: verify PBKDF2 hash
    Auth-->>Client: access JWT (60 min) + refresh JWT (7 days)
    Client->>API: Authorization: Bearer <access>
    API->>API: decode, check role, load active user
    API-->>Client: 200 / 401 / 403
```

| Роль | Чтение | PATCH/status | Issues | Reconcile | CRUD orders | Users |
|---|---|---|---|---|---|---|
| `viewer` | ✅ | — | — | — | — | — |
| `analyst` | ✅ | ✅ | ✅ | ✅ | — | — |
| `admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

## Кэш

- Ключи: `orderhub:orders:<hash>` и `orderhub:order:<hash>`.
- TTL: `ORDERHUB_CACHE_TTL_SECONDS` (по умолчанию 60 с).
- Инвалидация: любая запись в заказ, issue, reconciliation или пользователя.
- Заголовок `X-Cache: HIT|MISS`; счётчики в `/metrics`.
- Redis опционален: без `ORDERHUB_REDIS_URL` используется in-memory TTL.

## DQ-детекторы

`duplicate_1c`, `status_conflict`, `unit_mismatch`, `missing_customer`, `unknown_sku`,
`total_mismatch`, `negative_qty`, `orphan_production`, `orphan_warehouse`, `email_only`,
`duplicate_crm`, `duplicate_warehouse`, `mixed_unit`, `missing_conversion`,
`contradictory_conversion`, `coverage_gap`, `ambiguous_date`, `ambiguous_match`.

## Ограничения

- Эталонный файл полного интеграционного набора содержит исторические false positives
  (блочная формула генератора);
  сервис фиксирует реальные дефекты, а не подгоняется под эталон.
- Нет полноценного token revocation и rotation refresh-токенов.
- Нет merge/split заказов и очереди `MatchCandidate` для спорных совпадений.
