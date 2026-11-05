.PHONY: install format lint test test-all migrate seed bootstrap run docker-up docker-down deploy clean

PYTHON ?= .venv/Scripts/python.exe
PIP ?= uv pip install --python $(PYTHON)
ALEMBIC ?= .venv/Scripts/alembic.exe

install:
	uv venv .venv
	$(PIP) -e ".[dev]"

format:
	$(PYTHON) -m ruff format app tests scripts

lint:
	$(PYTHON) -m ruff format --check app tests scripts
	$(PYTHON) -m ruff check app tests scripts

test:
	$(PYTHON) -m pytest -q -m "not integration" --cov=app --cov-report=term-missing --cov-fail-under=80

test-all:
	$(PYTHON) -m pytest -q

migrate:
	$(ALEMBIC) upgrade head
	$(ALEMBIC) check

seed:
	$(PYTHON) -m app.cli seed

bootstrap:
	$(PYTHON) -m app.cli seed --source-dir data/reference
	$(PYTHON) -m app.cli reconcile --source-dir data/reference --run-date 2026-11-05

run:
	$(PYTHON) -m app.cli serve --port 8080

docker-up:
	docker-compose up -d --build

docker-down:
	docker-compose down

deploy:
	bash scripts/deploy.sh

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
