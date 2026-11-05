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
API_CID="$(docker-compose ps -q api)"
for _ in {1..30}; do
  STATUS="$(docker inspect -f '{{.State.Health.Status}}' "${API_CID}" 2>/dev/null || true)"
  if [ "${STATUS}" = "healthy" ]; then
    break
  fi
  sleep 1
done

echo "==> Smoke test"
docker-compose exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
docker-compose exec -T api python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/orders/stats').read().decode())"
echo "Deploy complete. Swagger UI: /docs"
