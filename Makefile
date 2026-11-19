
.PHONY: help up down logs ps test test-integration cov lint migrate seed

help:
	uv run poe

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps -a

test:
	uv run poe test

test-integration:
	uv run poe test-integration

cov:
	uv run poe cov

lint:
	uv run poe lint

migrate:
	uv run poe migrate

seed:
	uv run poe seed
