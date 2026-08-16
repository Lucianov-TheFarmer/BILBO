.PHONY: lint test run worker format ai-up ai-down ai-run full-up full-build full-down full-logs full-status rag-index rag-export rag-import

lint:
	ruff check app

test:
	pytest

run:
	uvicorn backend.main:app --host 0.0.0.0 --port 8890 --reload

worker:
	celery -A backend.tasks.celery_app.celery_app worker --loglevel=info --concurrency=1

format:
	ruff format app

ai-up:
	docker compose up -d qdrant ollama

ai-down:
	docker compose stop qdrant ollama

ai-run:
	test -n "$(DEG_FILE)"
	test -n "$(SHEET)"
	docker compose --profile ai run --rm cluster-rag --deg-xlsx /input/$(DEG_FILE) --sheet "$(SHEET)" --output-dir /output --run-id "$(or $(RUN_ID),standalone)"

full-up:
	docker compose up -d

full-build:
	docker compose up -d --build

full-down:
	docker compose down

full-logs:
	docker compose logs -f bioinfo worker

full-status:
	docker compose ps

rag-index:
	docker compose --profile rag-index run --rm rag-indexer

rag-export:
	test -n "$(EXPORT_NAME)"
	docker compose --profile rag-admin run --rm rag-admin export /rag/exports/$(EXPORT_NAME)

rag-import:
	test -n "$(EXPORT_NAME)"
	docker compose --profile rag-admin run --rm rag-admin import /rag/exports/$(EXPORT_NAME)
