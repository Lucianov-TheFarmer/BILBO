.PHONY: lint test run worker format

lint:
	ruff check app

test:
	pytest

run:
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

worker:
	celery -A backend.tasks.celery_app.celery_app worker --loglevel=info --concurrency=1

format:
	ruff format app
