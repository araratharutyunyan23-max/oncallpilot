# OncallPilot — Phase 0 dev commands. Run from the repo root: `make -f ops/Makefile <target>`
# (or symlink: `ln -s ops/Makefile Makefile` then `make <target>`).
SHELL := /bin/bash
COMPOSE := docker compose -f ops/docker-compose.yml

.PHONY: help bootstrap up down logs web agent-dev test lint fmt

help:
	@echo "bootstrap  install uv + agent/web deps, create .env"
	@echo "up         docker compose up --build (agent + web)"
	@echo "down       stop stack"
	@echo "logs       follow stack logs"
	@echo "agent-dev  run agent locally with reload (uv)"
	@echo "web        run web locally (npm)"
	@echo "test       agent unit tests"
	@echo "lint       ruff + mypy (agent) + tsc (web)"

bootstrap:
	command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
	cd services/agent && uv sync
	cd apps/web && npm install
	[ -f .env ] || cp .env.example .env
	@echo "→ set ANTHROPIC_API_KEY in .env, then: make up"

up:
	[ -f .env ] || cp .env.example .env
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

agent-dev:
	cd services/agent && uv run uvicorn app.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

db-up:
	$(COMPOSE) up -d postgres

ingest:
	cd services/agent && uv run python -m app.retrieval.ingest

eval-retrieval:
	cd services/agent && uv run python -m app.retrieval.evaluate

eval:
	cd services/agent && uv run python -m app.eval.run

eval-baseline:
	cd services/agent && uv run python -m app.eval.run --update-baseline

test:
	cd services/agent && uv run pytest -q

lint:
	cd services/agent && uv run ruff check . && uv run mypy app
	cd apps/web && npm run typecheck
