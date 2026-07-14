.PHONY: install db-up db-init api worker test eval lint

install:
	uv sync --extra dev

db-up:
	docker compose up -d db

db-init:
	uv run python scripts/init_db.py

api:
	uv run uvicorn app.main:app --reload --port 5275

worker:
	uv run procrastinate --app app.ingestion.worker.pq_app worker

test:
	uv run pytest -q

eval:
	uv run python evals/run_folder_eval.py

lint:
	uv run ruff check app tests evals scripts
