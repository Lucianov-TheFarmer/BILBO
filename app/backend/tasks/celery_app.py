from celery import Celery

from ..core.settings import settings


celery_app = Celery(
    "bilbo",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_default_retry_delay=30,
    task_annotations={"pipeline.execute": {"max_retries": 2}},
    broker_connection_retry_on_startup=True,
    timezone="UTC",
)
