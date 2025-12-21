"""
Celery tasks for background processing.
"""

from src.tasks.celery_app import app
from src.tasks import embedding_tasks

__all__ = ["app", "embedding_tasks"]
