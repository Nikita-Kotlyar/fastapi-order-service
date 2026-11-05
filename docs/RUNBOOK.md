# Runbook

## Запуск сервиса

```bash
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
cp .env.example .env
# Заполни JWT-секрет и пароли bootstrap-пользователей.

.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m app.cli seed
.venv/Scripts/python.exe -m app.cli reconcile --run-date 2026-11-05
.venv/Scripts/python.exe -m app.cli serve --port 8080
```

По умолчанию используется `data/reference` — эталонный набор из 16 заказов для
воспроизводимого запуска и интеграционных тестов. Для рабочего каталога выгрузок:

```bash
SOURCE_DATA_DIR=/data/source \
.venv/Scripts/python.exe -m app.cli reconcile --source-dir "$SOURCE_DATA_DIR" --run-date 2026-11-05
```

## Docker Compose

Compose требует `POSTGRES_PASSWORD` в `.env`/секрет-менеджере.

```bash
docker-compose up -d --build
docker-compose ps
docker-compose logs -f api
docker-compose exec api orderhub seed
docker-compose exec api orderhub reconcile --run-date 2026-11-05
```

Рабочий каталог выгрузок:

```bash
SOURCE_DATA_DIR=/data/source docker-compose up -d --build
```

Остановка:

```bash
docker-compose down          # данные PostgreSQL сохраняются в volume pgdata
docker-compose down -v       # удалить и БД
```

## Проверки здоровья

```bash
API_BASE_URL="${API_BASE_URL:?set API_BASE_URL}"

curl -s "$API_BASE_URL/health"
curl -s "$API_BASE_URL/ready"
curl -s "$API_BASE_URL/api/v1/orders/stats"
curl -s "$API_BASE_URL/metrics"
```

`/ready` проверяет PostgreSQL и кэш; каждый ответ содержит `X-Request-ID`.

## Пользователи и роли

Bootstrap-пользователи создаются при `ORDERHUB_SEED_DEFAULT_USERS=true` из
переменных `ORDERHUB_ADMIN_PASSWORD`, `ORDERHUB_ANALYST_PASSWORD`,
`ORDERHUB_VIEWER_PASSWORD`. Пароли задаются через секрет-менеджер и меняются
после первого входа. В репозитории секретов нет.

Создать пользователя:

```bash
.venv/Scripts/python.exe -m app.cli create-user --username qa --password "$QA_PASSWORD" --roles analyst
```

Для production выставь `ORDERHUB_SEED_DEFAULT_USERS=false` и создавай
пользователей через CLI или admin API.

## Миграции

```bash
alembic current
alembic upgrade head
alembic check
alembic downgrade -1
```

Перед миграцией в production сделай backup PostgreSQL.

## Кэш

Проверить ключи:

```bash
docker-compose exec redis redis-cli --scan --pattern 'orderhub:*'
```

Сбросить кэш:

```bash
docker-compose exec redis redis-cli --scan --pattern 'orderhub:*' | xargs -r docker-compose exec -T redis redis-cli del
```

Любая запись через API инвалидирует кэш автоматически.

## Типовые проблемы

| Симптом | Причина | Действие |
|---|---|---|
| `no such column: orders.is_manual` | не применены миграции | `alembic upgrade head` |
| `401 Incorrect username or password` | неверные креды или сброшенный пароль | проверь секрет-менеджер, при необходимости пересоздай пользователя |
| `403 One of the roles is required` | роль не подходит | войди как admin/analyst |
| `ready` возвращает `cache_ok: no` | Redis недоступен | проверь `docker-compose ps` и `ORDERHUB_REDIS_URL` |
| `coverage` падает в CI | меньше 80% | добавь тест, не понижай порог |
| Docker build падает на `data/reference` | эталонный набор отсутствует | `python scripts/build_reference_dataset.py` |

## Backup / restore PostgreSQL

```bash
docker-compose exec -T db pg_dump -U orderhub orderhub > backup.sql
cat backup.sql | docker-compose exec -T db psql -U orderhub -d orderhub
```
