from celery import Celery

from app.core.config import settings


celery_app = Celery("meeting_ai", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_always_eager=settings.task_always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_routes={"app.tasks.jobs.*": {"queue": "recordings"}},
)
