"""
Celery Configuration for Background Job Processing
"""

import os
from celery import Celery


def make_celery(app_name='flock'):
    """
    Create and configure Celery app

    Args:
        app_name: Name of the application

    Returns:
        Configured Celery instance
    """
    # Get Redis URL from environment
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Create Celery instance
    celery_app = Celery(
        app_name,
        broker=redis_url,
        backend=redis_url
    )

    # Configure Celery
    celery_app.conf.update(
        # Serialization
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],

        # Timezone
        timezone='UTC',
        enable_utc=True,

        # Task tracking
        task_track_started=True,
        task_send_sent_event=True,

        # Worker configuration
        worker_send_task_events=True,
        worker_prefetch_multiplier=4,
        worker_max_tasks_per_child=1000,

        # Result backend
        result_expires=3600,  # Results expire after 1 hour

        # Task routing (can add custom routing later)
        task_routes={
            'tasks.process_document_task': {'queue': 'documents'},
            'tasks.classify_document_task': {'queue': 'classification'},
            'tasks.generate_employee_embeddings_task': {'queue': 'embeddings'},
            'tasks.sync_google_drive_task': {'queue': 'sync'},
        },

        # Task time limits
        task_soft_time_limit=600,  # 10 minutes soft limit
        task_time_limit=900,  # 15 minutes hard limit

        # Retry configuration
        task_acks_late=True,
        task_reject_on_worker_lost=True,

        # Connection retry settings for Celery 6.0+ compatibility
        broker_connection_retry_on_startup=True,
        broker_connection_retry=True,
        broker_connection_max_retries=10,

        # Health check to detect broken connections
        broker_heartbeat=10,
        broker_pool_limit=10,

        # Worker cancel tasks on connection loss
        worker_cancel_long_running_tasks_on_connection_loss=False,
    )

    return celery_app


# Create global Celery instance
celery_app = make_celery()


# Celery Beat schedule for periodic tasks (to be added in future sprints)
celery_app.conf.beat_schedule = {
    # Example: Run memory consolidation nightly at 2 AM
    # 'consolidate-memories': {
    #     'task': 'tasks.consolidate_memories_task',
    #     'schedule': crontab(hour=2, minute=0),
    # },
}
