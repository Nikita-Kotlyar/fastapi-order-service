## What changed

<!-- Кратко: что и зачем. -->

## How to verify

```bash
ruff format --check app tests scripts
ruff check app tests scripts
pytest -q -m "not integration" --cov=app --cov-fail-under=80
```

## Checklist

- [ ] Тесты добавлены/обновлены
- [ ] Миграция добавлена, `alembic check` без diff
- [ ] README/OpenAPI обновлены при изменении API
- [ ] Секреты не попали в diff
- [ ] Роли и права проверены
