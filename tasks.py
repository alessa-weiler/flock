"""
Background Tasks for Document Processing
Sprint 2: Now includes smart chunking, embeddings, and vector storage
"""

import os
import json
import tempfile
from typing import Dict, Any
from celery_config import celery_app
from document_processor import DocumentExtractor
from storage_manager import StorageManager
from text_chunker import SmartChunker
from embedding_service import EmbeddingService
from vector_store import VectorStore
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
            SET metadata_json = %s
            WHERE id = %s
        ''', (json.dumps(extraction_result['metadata']), doc_id))
        conn.commit()

        update_job_status(job_id, 'running', 40)

        # ============================================================================
        # SPRINT 2: Smart Chunking with Token Counting
        # ============================================================================
        text = extraction_result['text']

        if not text or not text.strip():
            print(f"Warning: No text extracted from document {doc_id}")
            # Mark as completed with warning
            cursor.execute('''
                UPDATE documents SET processing_status = 'completed' WHERE id = %s
            ''', (doc_id,))
            conn.commit()

            result = {
                'doc_id': doc_id,
                'filename': doc['filename'],
                'chunks_created': 0,
                'extraction_method': extraction_result.get('extraction_method'),
                'char_count': 0,
                'warning': 'No text content extracted',
                'metadata': extraction_result['metadata']
            }
            update_job_status(job_id, 'completed', 100, result=result)
            conn.close()
            return result

        print(f"Chunking text with SmartChunker (1000 tokens, 200 overlap)")
        chunker = SmartChunker(chunk_size=1000, overlap=200)

        chunk_metadata = {
            'doc_id': doc_id,
            'filename': doc['filename'],
            'doc_type': doc['file_type']
        }

        chunks = chunker.chunk_document(text, chunk_metadata)
        print(f"Created {len(chunks)} chunks")

        update_job_status(job_id, 'running', 50)

        # ============================================================================
        # SPRINT 2: Generate Embeddings
        # ============================================================================
        print(f"Generating embeddings for {len(chunks)} chunks")
        embedding_service = EmbeddingService(model="text-embedding-3-large")

        # Extract text from chunks for embedding
        chunk_texts = [chunk['text'] for chunk in chunks]

        try:
            embeddings = embedding_service.generate_embeddings_batched(
                texts=chunk_texts,
                org_id=org_id,
                batch_size=100
            )
            print(f"✓ Generated {len(embeddings)} embeddings")
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            # Rollback: don't store incomplete data
            cursor.execute('UPDATE documents SET processing_status = %s WHERE id = %s', ('failed', doc_id))
            conn.commit()
            conn.close()
            raise Exception(f"Embedding generation failed: {e}")

        update_job_status(job_id, 'running', 70)

        # ============================================================================
        # SPRINT 2: Store in Pinecone Vector Store
        # ============================================================================
        print(f"Storing embeddings in Pinecone")
        vector_store = VectorStore(index_name="flock-knowledge-base")

        try:
            upsert_result = vector_store.upsert_document_chunks(
                org_id=org_id,
                doc_id=doc_id,
                chunks=chunks,
                embeddings=embeddings,
                metadata={
                    'filename': doc['filename'],
                    'doc_type': doc['file_type'],
                    'upload_date': str(doc.get('upload_date', ''))
                }
            )
            print(f"✓ Stored {upsert_result['upserted_count']} vectors in Pinecone")
        except Exception as e:
            print(f"Error storing in Pinecone: {e}")
            # Rollback embeddings and chunks
            cursor.execute('DELETE FROM document_chunks WHERE document_id = %s', (doc_id,))
            cursor.execute('UPDATE documents SET processing_status = %s WHERE id = %s', ('failed', doc_id))
            conn.commit()
            conn.close()
            raise Exception(f"Vector storage failed: {e}")

        update_job_status(job_id, 'running', 85)

        # ============================================================================
        # Store Chunks in PostgreSQL (with embedding IDs and token counts)
        # ============================================================================
        print(f"Storing chunks in database")
        for idx, chunk in enumerate(chunks):
            embedding_id = f"doc_{doc_id}_chunk_{idx}"
            cursor.execute('''
                INSERT INTO document_chunks (
                    document_id, chunk_text, chunk_index, token_count,
                    embedding_id, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                doc_id,
                chunk['text'],
                chunk['index'],
                chunk['tokens'],
                embedding_id,
                json.dumps(chunk.get('metadata', {}))
            ))

        # Mark document as completed
        cursor.execute('''
            UPDATE documents SET processing_status = 'completed' WHERE id = %s
        ''', (doc_id,))

        conn.commit()

        update_job_status(job_id, 'running', 90)

        # ============================================================================
        # Classify Document (Sprint 3)
        # ============================================================================
        print(f"Classifying document")
        try:
            from document_classifier import DocumentClassifier
            classifier = DocumentClassifier()

            # Get organization context for better classification
            org_context = classifier.get_org_context(org_id)

            # Classify the document
            classification = classifier.classify(
                document_text=text,
                filename=doc['filename'],
                org_context=org_context
            )

            # Store classification in database
            cursor.execute('''
                INSERT INTO document_classifications (
                    document_id, organization_id, team, project, doc_type,
                    time_period, confidentiality_level, mentioned_people,
                    tags, summary, confidence_scores, classified_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (document_id)
                DO UPDATE SET
                    team = EXCLUDED.team,
                    project = EXCLUDED.project,
                    doc_type = EXCLUDED.doc_type,
                    time_period = EXCLUDED.time_period,
                    confidentiality_level = EXCLUDED.confidentiality_level,
                    mentioned_people = EXCLUDED.mentioned_people,
                    tags = EXCLUDED.tags,
                    summary = EXCLUDED.summary,
                    confidence_scores = EXCLUDED.confidence_scores,
                    classified_at = NOW()
            ''', (
                doc_id,
                org_id,
                classification.get('team'),
                classification.get('project'),
                classification.get('doc_type'),
                classification.get('time_period'),
                classification.get('confidentiality_level'),
                json.dumps(classification.get('mentioned_people', [])),
                json.dumps(classification.get('tags', [])),
                classification.get('summary'),
                json.dumps(classification.get('confidence_scores', {}))
            ))

            conn.commit()
            print(f"✓ Document classified: {classification.get('doc_type')} - {classification.get('team')} - {classification.get('project')}")

        except Exception as e:
            print(f"Warning: Classification failed: {e}")
            # Don't fail the entire job if classification fails
            classification = None

        update_job_status(job_id, 'running', 95)

        # Clean up temp file
        os.remove(temp_file)
        os.rmdir(temp_dir)

        # Mark job as completed with enhanced result info
        total_tokens = sum(chunk['tokens'] for chunk in chunks)
        result = {
            'doc_id': doc_id,
            'filename': doc['filename'],
            'chunks_created': len(chunks),
            'total_tokens': total_tokens,
            'embeddings_generated': len(embeddings),
            'vectors_stored': upsert_result['upserted_count'],
            'extraction_method': extraction_result.get('extraction_method'),
            'char_count': len(text),
            'metadata': extraction_result['metadata'],
            'classification': classification if classification else None
        }

        update_job_status(job_id, 'completed', 100, result=result)

        conn.close()

        print(f"✓ Successfully processed document {doc_id}: {len(chunks)} chunks, {total_tokens} tokens")
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
    Classify or re-classify a document using GPT-4 (Sprint 3)

    This task can be used to:
    - Re-classify a document after manual edits
    - Classify documents that failed classification during processing
    - Update classification when organization context changes

    Args:
        doc_id: Document ID

    Returns:
        Classification results
    """
    from document_classifier import DocumentClassifier

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get document details
        cursor.execute('''
            SELECT d.id, d.filename, d.organization_id, d.processing_status,
                   string_agg(dc.chunk_text, ' ' ORDER BY dc.chunk_index) as full_text
            FROM documents d
            LEFT JOIN document_chunks dc ON dc.document_id = d.id
            WHERE d.id = %s
            GROUP BY d.id, d.filename, d.organization_id, d.processing_status
        ''', (doc_id,))

        doc = cursor.fetchone()

        if not doc:
            raise Exception(f"Document {doc_id} not found")

        if not doc['full_text']:
            raise Exception(f"Document {doc_id} has no text content (chunks not found)")

        if doc['processing_status'] != 'completed':
            raise Exception(f"Document {doc_id} is not fully processed (status: {doc['processing_status']})")

        org_id = doc['organization_id']
        text = doc['full_text']
        filename = doc['filename']

        print(f"Classifying document {doc_id}: {filename} (org: {org_id})")

        # Initialize classifier
        classifier = DocumentClassifier()

        # Get organization context
        org_context = classifier.get_org_context(org_id)

        # Classify the document
        classification = classifier.classify(
            document_text=text,
            filename=filename,
            org_context=org_context
        )

        # Store classification in database
        cursor.execute('''
            INSERT INTO document_classifications (
                document_id, organization_id, team, project, doc_type,
                time_period, confidentiality_level, mentioned_people,
                tags, summary, confidence_scores, classified_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (document_id)
            DO UPDATE SET
                team = EXCLUDED.team,
                project = EXCLUDED.project,
                doc_type = EXCLUDED.doc_type,
                time_period = EXCLUDED.time_period,
                confidentiality_level = EXCLUDED.confidentiality_level,
                mentioned_people = EXCLUDED.mentioned_people,
                tags = EXCLUDED.tags,
                summary = EXCLUDED.summary,
                confidence_scores = EXCLUDED.confidence_scores,
                classified_at = NOW()
        ''', (
            doc_id,
            org_id,
            classification.get('team'),
            classification.get('project'),
            classification.get('doc_type'),
            classification.get('time_period'),
            classification.get('confidentiality_level'),
            json.dumps(classification.get('mentioned_people', [])),
            json.dumps(classification.get('tags', [])),
            classification.get('summary'),
            json.dumps(classification.get('confidence_scores', {}))
        ))

        conn.commit()
        conn.close()

        print(f"✓ Document {doc_id} classified: {classification.get('doc_type')} - {classification.get('team')} - {classification.get('project')}")

        return {
            'status': 'success',
            'doc_id': doc_id,
            'classification': classification
        }

    except Exception as e:
        error_msg = str(e)
        print(f"Error classifying document {doc_id}: {error_msg}")

        # Retry logic
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        else:
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'error': error_msg
            }


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


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_employee_embeddings_task(self, org_id: int, user_id: int):
    """
    Generate embeddings for employee profile

    Args:
        org_id: Organization ID
        user_id: User ID

    Returns:
        Embedding generation results
    """
    job_id = self.request.id

    try:
        print(f"Generating employee embedding for user_id={user_id}, org_id={org_id}")

        # Get user profile from database
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT u.id, u.full_name, u.email,
                   up.bio, up.specialties, up.years_experience, up.education,
                   up.current_position
            FROM users u
            LEFT JOIN user_profiles up ON u.id = up.user_id
            WHERE u.id = %s
        ''', (user_id,))

        user = cursor.fetchone()

        if not user:
            raise Exception(f"User {user_id} not found")

        # Create text representation of employee profile
        profile_parts = []

        if user.get('full_name'):
            profile_parts.append(f"Name: {user['full_name']}")

        if user.get('current_position'):
            profile_parts.append(f"Position: {user['current_position']}")

        if user.get('years_experience'):
            profile_parts.append(f"Experience: {user['years_experience']} years")

        if user.get('specialties'):
            profile_parts.append(f"Specialties: {user['specialties']}")

        if user.get('education'):
            profile_parts.append(f"Education: {user['education']}")

        if user.get('bio'):
            profile_parts.append(f"Bio: {user['bio']}")

        profile_text = " | ".join(profile_parts)

        if not profile_text.strip():
            print(f"Warning: No profile data for user {user_id}, skipping embedding")
            return {'status': 'skipped', 'message': 'No profile data available'}

        print(f"Profile text: {profile_text[:200]}...")

        # Generate embedding
        embedding_service = EmbeddingService(model="text-embedding-3-large")
        embedding = embedding_service.generate_single_embedding(profile_text, org_id)

        print(f"✓ Generated embedding with {len(embedding)} dimensions")

        # Store in Pinecone
        vector_store = VectorStore(index_name="flock-knowledge-base")

        metadata = {
            'name': user.get('full_name', ''),
            'title': user.get('current_position', ''),
            'email': user.get('email', ''),
            'specialties': user.get('specialties', ''),
            'experience': user.get('years_experience', 0),
            'profile_text': profile_text[:500]  # Limit to 500 chars
        }

        upsert_result = vector_store.upsert_employee_embedding(
            org_id=org_id,
            user_id=user_id,
            embedding=embedding,
            metadata=metadata
        )

        print(f"✓ Stored employee embedding in Pinecone")

        # Store snapshot in database
        cursor.execute('''
            INSERT INTO employee_embeddings (
                user_id, organization_id, embedding_id, profile_snapshot_json, last_updated
            )
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, organization_id)
            DO UPDATE SET
                embedding_id = EXCLUDED.embedding_id,
                profile_snapshot_json = EXCLUDED.profile_snapshot_json,
                last_updated = CURRENT_TIMESTAMP
        ''', (
            user_id,
            org_id,
            upsert_result['vector_id'],
            json.dumps({
                'name': user.get('full_name'),
                'title': user.get('current_position'),
                'profile_text': profile_text
            })
        ))

        conn.commit()
        conn.close()

        result = {
            'user_id': user_id,
            'org_id': org_id,
            'vector_id': upsert_result['vector_id'],
            'name': user.get('full_name'),
            'status': 'completed'
        }

        print(f"✓ Successfully generated employee embedding for user {user_id}")
        return result

    except Exception as e:
        error_msg = str(e)
        print(f"Error generating employee embedding: {error_msg}")

        # Retry logic
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        else:
            raise
