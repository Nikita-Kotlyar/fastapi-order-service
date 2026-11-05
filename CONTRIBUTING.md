# Contributing

## Setup

```bash
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
pre-commit install
```

## Before a PR

```bash
ruff format app tests scripts
ruff check app tests scripts
pytest -q -m "not integration" --cov=app --cov-fail-under=80
alembic upgrade head && alembic check
```

Для полного прогона с интеграционным набором:

```bash
pytest -q
```

## Rules

- Один PR — одна тема.
- Новые эндпоинты: Pydantic-схема, тест, запись в README/OpenAPI.
- Изменение схемы БД: Alembic-миграция + `alembic check` без diff.
- Секреты только в `.env`; `.env.example` обновляется при добавлении переменной.
- Деньги — только `Decimal`; даты — только `date`.
- Не подгонять DQ-детекторы под эталонные false positives.
- Для новой роли обнови матрицу в `docs/ARCHITECTURE.md` и тесты RBAC.

## Commit style

`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`.
