#!/usr/bin/env bash
# CD: build, migrate, seed, reconcile and smoke-test the Compose stack.
set -euo pipefail

cd "$(dirname "$0")/.."
RUN_DATE="${RUN_DATE:-2026-11-05}"
SOURCE_DATA_DIR="${SOURCE_DATA_DIR:-./data/reference}"
export SOURCE_DATA_DIR
# Git Bash converts /data/source to a Windows path before passing it to docker.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

echo "==> Building and starting containers (source data: ${SOURCE_DATA_DIR})"
docker-compose up -d --build

echo "==> Applying migrations"
docker-compose exec -T api alembic upgrade head

echo "==> Seeding master data and users"
docker-compose exec -T api orderhub seed

echo "==> Reconciling order sources"
# The container gets ORDERHUB_SOURCE_DIR=/data/source from docker-compose.yml.
docker-compose exec -T api orderhub reconcile --run-date "${RUN_DATE}" >/dev/null

echo "==> Waiting for API"
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> Smoke test"
curl -fsS http://127.0.0.1:8080/health
echo
curl -fsS http://127.0.0.1:8080/api/v1/orders/stats
echo
echo "Deploy complete. Swagger: http://127.0.0.1:8080/docs"
