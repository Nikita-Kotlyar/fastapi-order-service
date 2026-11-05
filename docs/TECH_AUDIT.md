# Аудит технологий и интеграционная проверка

Дата: 2026-11-05.

## Матрица

| Технология | Статус | Доказательство |
|---|---|---|
| Python 3.12+ | ✅ | venv 3.13, весь код |
| FastAPI | ✅ | 24 пути в OpenAPI, Swagger UI |
| Pydantic v2 | ✅ | схемы API и настройки |
| SQLAlchemy 2.x | ✅ | 16 таблиц, PostgreSQL и SQLite |
| Alembic | ✅ | 3 ревизии, `alembic check` без diff |
| PostgreSQL | ✅ | PostgreSQL 16.15, golden-тест на 580 заказов |
| Redis | ✅ | Redis 7.4.12, ключи `orderhub:*`, `X-Cache`, инвалидация |
| Docker | ✅ | образ собран, non-root, healthcheck |
| Docker Compose | ✅ | 3 контейнера healthy, миграции при старте |
| REST CRUD | ✅ | GET/POST/PATCH/DELETE, тесты |
| Авторизация | ✅ | JWT access/refresh, users в PostgreSQL, роли admin/analyst/viewer |
| Пагинация | ✅ | `limit`/`offset` + `total` |
| Кэш | ✅ | TTL, Redis/in-memory, `HIT/MISS`, инвалидация |
| pytest | ✅ | 53 теста на полном наборе, coverage 90.8% |
| CI | ✅ | SQLite + PostgreSQL + Redis + Docker |
| CD | 🟡 | `scripts/deploy.sh` и GHCR publish; cloud deploy не автоматизирован |
| OpenAPI | ✅ | security scheme, теги, схемы, параметры |

## Интеграционная проверка

```text
PostgreSQL 16.15
Redis 7.4.12
Docker 29.7.2

orderhub-api     Up   :8080 -> 8000   (healthy, non-root)
orderhub-db      Up   :5432 -> 5432   (healthy)
orderhub-redis   Up   :6379 -> 6379   (healthy)
```

Проверено:

- `alembic upgrade head` на PostgreSQL, `alembic_version = 18bba6cc7f28`.
- Покрытие источников: 400 / 309 / 183 / 250 / 200.
- 580 канонических заказов, 993 проблемы, повторная сверка без дублей.
- Полный pytest против PostgreSQL и Redis: 53 passed, 0 skipped.
- `POST /api/v1/orders` → 201, `DELETE` → 204, повторный `GET` → 404.
- Redis: ключ `orderhub:orders:*` после GET, удаление после POST/DELETE.
- `/ready` возвращает `database: ok`, `cache: redis`, `cache_ok: yes`.
- Swagger UI: `http://127.0.0.1:8080/docs`.

## Ограничения

- CD не разворачивает Kubernetes/облако.
- Нет token revocation и rotation refresh-токенов.
- Нет `MatchCandidate` / merge / split.
