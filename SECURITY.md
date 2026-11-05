# Security

## Reporting

If you find a vulnerability, open an issue with the `security` label and do not
publish an exploit before the maintainers respond.

## Secrets

- `ORDERHUB_JWT_SECRET` — не короче 32 байт, только из секрет-менеджера.
- Пароли пользователей хранятся как PBKDF2-SHA256 с индивидуальной солью.
- `.env` в `.gitignore`; в репозитории только `.env.example` с placeholders.
- Bootstrap-пароли задаются через `ORDERHUB_*_PASSWORD` и меняются после первого входа.

## Production checklist

- [ ] `ORDERHUB_SEED_DEFAULT_USERS=false`
- [ ] Уникальные пароли для admin/analyst/viewer
- [ ] `ORDERHUB_JWT_SECRET` из секрет-менеджера
- [ ] PostgreSQL и Redis не опубликованы наружу
- [ ] HTTPS/ingress перед API
- [ ] Ротация refresh-токенов и revocation (пока не реализованы)
- [ ] Backup PostgreSQL и мониторинг `/ready`, `/metrics`
