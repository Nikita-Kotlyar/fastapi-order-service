# Changelog

## 0.1.0 — 2026-11-05

### Added

- Ingestion пяти источников: 1С, CRM, почта, производство, склад.
- Нормализация дат, Decimal, единиц, статусов, SKU и клиентов.
- Матчинг exact + fuzzy, golden record, провенанс, 18 DQ-детекторов.
- REST CRUD заказов, пагинация, фильтры, CSV export, OpenAPI.
- JWT access/refresh, пользователи в PostgreSQL, роли admin/analyst/viewer.
- Redis-кэш с TTL, `X-Cache`, инвалидацией и метриками.
- Alembic-миграции, PostgreSQL 16, Docker Compose, CI (SQLite/PostgreSQL/Redis/Docker).
- 53 теста, coverage 90.8%, live-проверка на PostgreSQL 16 и Redis 7.
- Эталонный набор `data/reference` на 16 заказов для интеграционных тестов.
