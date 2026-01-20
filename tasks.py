"""
Celery Tasks Entry Point

This file serves as the entry point for Celery workers.
It sets up the Python path and imports all task definitions.
"""

import os
import sys

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'documents'))

# Import celery app and tasks
from celery_config import celery_app
from tasks import (
    process_document_task,
    classify_document_task,
    generate_employee_embeddings_task,
    sync_google_drive_task
)

# Make celery_app available at module level for Celery to find
__all__ = [
    'celery_app',
    'process_document_task',
    'classify_document_task',
    'generate_employee_embeddings_task',
    'sync_google_drive_task'
]
