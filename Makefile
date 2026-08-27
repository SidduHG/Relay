.PHONY: install up down logs test lint migrate load chaos

install:
	uv sync --all-packages

up:
	docker compose -f infra/compose/docker-compose.yml up --build

down:
	docker compose -f infra/compose/docker-compose.yml down -v

logs:
	docker compose -f infra/compose/docker-compose.yml logs -f

test: install
	uv run pytest

lint: install
	uv run ruff check .
	uv run mypy .

migrate:
	uv run --project apps/api alembic -c migrations/alembic.ini upgrade head

load:
	@echo "load harness lands with F9 — see tests/load"

chaos:
	@echo "chaos suite lands with F3/F10 — see tests/chaos"
