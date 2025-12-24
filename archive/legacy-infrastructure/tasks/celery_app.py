"""
Celery application for async background tasks.

Handles:
- Async embedding generation
- Batch processing
- Paper indexing
"""

from celery import Celery
from kombu import Exchange, Queue
from loguru import logger

from config.settings import settings

# Create Celery app
app = Celery(
    "literature-ai",
    broker=settings.redis.url,
    backend=settings.redis.url,
)

# Celery configuration
app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # 9 minutes soft limit

    # Results
    result_expires=3600,  # Keep results for 1 hour
    result_extended=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time (GPU constraint)
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks (prevent memory leaks)

    # Task routing
    task_routes={
        "src.tasks.embedding_tasks.*": {"queue": "embeddings"},
        "src.tasks.agent_tasks.*": {"queue": "agents"},
    },

    # Queues
    task_queues=(
        Queue("embeddings", Exchange("embeddings"), routing_key="embeddings"),
        Queue("agents", Exchange("agents"), routing_key="agents"),
        Queue("default", Exchange("default"), routing_key="default"),
    ),
)

logger.info("Celery app configured")
