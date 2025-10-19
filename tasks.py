"""
Background Tasks for Document Processing
"""

import os
import json
import tempfile
from typing import Dict, Any
from celery_config import celery_app
from document_processor import DocumentExtractor
from storage_manager import StorageManager
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get PostgreSQL database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise Exception("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def update_job_status(job_id: str, status: str, progress: int, error: str = None, result: Dict = None):
    """
    Update processing job status in database

    Args:
        job_id: Celery task ID
        status: Job status (queued, running, completed, failed)
        progress: Progress percentage (0-100)
        error: Error message if failed
        result: Result data if completed
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        update_fields = {
            'status': status,
            'progress': progress
        }

        if error:
            update_fields['error_message'] = error

        if result:
            update_fields['result_json'] = json.dumps(result)

        if status == 'running':
            cursor.execute('''
                UPDATE processing_jobs
                SET status = %s, progress = %s, started_at = CURRENT_TIMESTAMP,
                    error_message = %s, result_json = %s
                WHERE job_id = %s
            ''', (status, progress, error, json.dumps(result) if result else None, job_id))
        elif status == 'completed' or status == 'failed':
            cursor.execute('''
                UPDATE processing_jobs
                SET status = %s, progress = %s, completed_at = CURRENT_TIMESTAMP,
                    error_message = %s, result_json = %s
                WHERE job_id = %s
            ''', (status, progress, error, json.dumps(result) if result else None, job_id))
        else:
            cursor.execute('''
                UPDATE processing_jobs
                SET status = %s, progress = %s, error_message = %s, result_json = %s
                WHERE job_id = %s
            ''', (status, progress, error, json.dumps(result) if result else None, job_id))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating job status: {e}")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, doc_id: int, org_id: int):
    """
    Background task to process uploaded document

    Args:
        doc_id: Document ID
        org_id: Organization ID

    Returns:
        Dict with processing results
    """
    job_id = self.request.id

    try:
        # Update job status to running
        update_job_status(job_id, 'running', 0)

        # Get document info from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM documents WHERE id = %s AND organization_id = %s', (doc_id, org_id))
        doc = cursor.fetchone()

        if not doc:
            raise Exception(f"Document {doc_id} not found")

        print(f"Processing document {doc_id}: {doc['filename']}")

        # Update document status to processing
        cursor.execute('''
            UPDATE documents SET processing_status = 'processing' WHERE id = %s
        ''', (doc_id,))
        conn.commit()

        # Update progress
        update_job_status(job_id, 'running', 10)

        # Download file from storage to temp location
        storage = StorageManager()
        temp_dir = tempfile.mkdtemp()
        temp_file = os.path.join(temp_dir, doc['filename'])

        print(f"Downloading file from {doc['storage_url']}")
        storage.download_to_temp(doc['storage_url'], temp_file)

        update_job_status(job_id, 'running', 30)

        # Extract text and metadata
        print(f"Extracting text from {doc['file_type']} file")
        extractor = DocumentExtractor()
        extraction_result = extractor.extract(temp_file, doc['file_type'])

        update_job_status(job_id, 'running', 60)

        # Get file system metadata
        file_metadata = extractor.extract_metadata_from_file(temp_file)
        extraction_result['metadata'].update(file_metadata)

        # Store extracted text and metadata in database
        print(f"Storing extraction results in database")
        cursor.execute('''
            UPDATE documents
            SET processing_status = 'completed',
                metadata_json = %s
            WHERE id = %s
        ''', (json.dumps(extraction_result['metadata']), doc_id))

        # Store text chunks (basic chunking for now - will be enhanced in Sprint 2)
        text = extraction_result['text']
        chunk_size = 5000  # Simple character-based chunking for Sprint 1
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

        for idx, chunk in enumerate(chunks):
            cursor.execute('''
                INSERT INTO document_chunks (document_id, chunk_text, chunk_index, metadata_json)
                VALUES (%s, %s, %s, %s)
            ''', (doc_id, chunk, idx, json.dumps({'page': 'multiple', 'method': 'basic'})))

        conn.commit()

        update_job_status(job_id, 'running', 90)

        # Clean up temp file
        os.remove(temp_file)
        os.rmdir(temp_dir)

        # Mark job as completed
        result = {
            'doc_id': doc_id,
            'filename': doc['filename'],
            'chunks_created': len(chunks),
            'extraction_method': extraction_result.get('extraction_method'),
            'char_count': len(text),
            'metadata': extraction_result['metadata']
        }

        update_job_status(job_id, 'completed', 100, result=result)

        conn.close()

        print(f"Successfully processed document {doc_id}")
        return result

    except Exception as e:
        error_msg = str(e)
        print(f"Error processing document {doc_id}: {error_msg}")

        # Update document status to failed
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE documents SET processing_status = 'failed' WHERE id = %s
            ''', (doc_id,))
            conn.commit()
            conn.close()
        except:
            pass

        # Update job status to failed
        update_job_status(job_id, 'failed', 0, error=error_msg)

        # Retry logic
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        else:
            raise


@celery_app.task(bind=True, max_retries=2)
def classify_document_task(self, doc_id: int):
    """
    Classify document using LLM (placeholder for Sprint 3)

    Args:
        doc_id: Document ID

    Returns:
        Classification results
    """
    # This will be implemented in Sprint 3 (Auto-Classification & Smart Folders)
    print(f"Classification task for document {doc_id} - not yet implemented")
    return {'status': 'pending', 'message': 'Classification not yet implemented'}


@celery_app.task(bind=True)
def sync_google_drive_task(self, org_id: int):
    """
    Sync files from Google Drive (placeholder for Sprint 1, full implementation later)

    Args:
        org_id: Organization ID

    Returns:
        Sync results
    """
    # This will be implemented later in Sprint 1
    print(f"Google Drive sync for org {org_id} - not yet implemented")
    return {'status': 'pending', 'message': 'Google Drive sync not yet implemented'}


@celery_app.task(bind=True)
def generate_employee_embeddings_task(self, org_id: int, user_id: int):
    """
    Generate embeddings for employee profile (placeholder for Sprint 2)

    Args:
        org_id: Organization ID
        user_id: User ID

    Returns:
        Embedding generation results
    """
    # This will be implemented in Sprint 2 (Embeddings & Vector Store)
    print(f"Employee embedding generation for user {user_id} - not yet implemented")
    return {'status': 'pending', 'message': 'Employee embeddings not yet implemented'}
