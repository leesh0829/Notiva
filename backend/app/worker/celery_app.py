"""Celery app skeleton for production wiring.

In production, define broker/backend URLs via env and register real tasks.
"""

from celery import Celery

celery_app = Celery("recording_ai")
celery_app.conf.update(
    broker_url="redis://localhost:6379/0",
    result_backend="redis://localhost:6379/1",
)
