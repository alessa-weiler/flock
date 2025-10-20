# Knowledge Platform Setup Guide

This guide covers the setup and configuration of the Knowledge Platform features for non-therapy organizations in Flock.

## Overview

The Knowledge Platform provides:
- Document upload and storage (PDF, DOCX, TXT, MD, CSV)
- Automatic text extraction and processing
- Background job processing with Celery
- Cloud storage with DigitalOcean Spaces
- **✅ Sprint 2: Smart text chunking with tiktoken**
- **✅ Sprint 2: OpenAI embeddings (text-embedding-3-large)**
- **✅ Sprint 2: Pinecone vector database for semantic search**
- **✅ Sprint 2: Document and employee semantic search APIs**
- Future: AI chat interface, auto-classification, smart folders

---

## Prerequisites

### System Requirements
- Python 3.11+
- PostgreSQL database
- Redis server
- Tesseract OCR (for scanned PDF support)

### macOS Installation

```bash
# Install Redis
brew install redis

# Install Tesseract OCR
brew install tesseract

# Install poppler (for pdf2image)
brew install poppler

# Install libmagic (for file type validation)
brew install libmagic
```

### Linux Installation

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install redis-server tesseract-ocr poppler-utils libmagic1 libmagic-dev

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

---

## Environment Configuration

### 1. Install Python Dependencies

```bash
cd flock
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Update `.env` file with the following configuration:

```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# DigitalOcean Spaces Configuration
DO_SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com
DO_SPACES_KEY=your_spaces_access_key
DO_SPACES_SECRET=your_spaces_secret_key
DO_SPACES_REGION=nyc3
DO_SPACES_BUCKET=flock-documents
```

---

## DigitalOcean Spaces Setup

### 1. Create a Space

1. Log in to [DigitalOcean](https://cloud.digitalocean.com)
2. Navigate to **Spaces** in the sidebar
3. Click **Create a Space**
4. Choose a region (e.g., NYC3)
5. Name your Space: `flock-documents`
6. Set file listing to **Private** (recommended)
7. Click **Create a Space**

### 2. Generate API Keys

1. Go to **API** → **Spaces Keys**
2. Click **Generate New Key**
3. Name it: `flock-knowledge-platform`
4. Copy the **Access Key** and **Secret Key**
5. Add them to your `.env` file:
   ```
   DO_SPACES_KEY=your_access_key_here
   DO_SPACES_SECRET=your_secret_key_here
   ```

### 3. Configure CORS (for frontend uploads)

1. Open your Space
2. Go to **Settings** → **CORS Configurations**
3. Add the following configuration:

```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["https://yourdomain.com", "http://localhost:8080"],
      "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
      "AllowedHeaders": ["*"],
      "MaxAgeSeconds": 3600
    }
  ]
}
```

---

## Database Setup

The knowledge platform tables are automatically created when you run the application. The following tables will be created:

- `documents` - Stores document metadata
- `document_chunks` - Text chunks for processing
- `document_classifications` - Auto-classification results
- `employee_embeddings` - Employee profile embeddings
- `chat_conversations` - Chat history
- `chat_messages` - Individual messages
- `google_drive_sync` - Google Drive integration settings
- `processing_jobs` - Background job tracking
- `embedding_usage` - Cost tracking

### Manual Database Initialization

If you need to manually initialize the tables:

```bash
# Start Python and run:
python
>>> from app import user_auth
>>> user_auth.init_user_database()
>>> exit()
```

---

## Running the Application

### 1. Start Redis Server

```bash
# macOS
redis-server

# Linux (if not running as service)
sudo systemctl start redis-server

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### 2. Start Celery Worker

In a separate terminal window:

```bash
cd flock
celery -A tasks worker --loglevel=info
```

You should see output like:
```
 -------------- celery@hostname v5.3.4
---- **** -----
--- * ***  * -- Darwin
-- * - **** ---
- ** ---------- [config]
- ** ---------- .> app:         flock:0x...
- ** ---------- .> transport:   redis://localhost:6379/0
- ** ---------- .> results:     redis://localhost:6379/0
- *** --- * --- .> concurrency: 8 (prefork)
-- ******* ---- .> task events: ON
--- ***** -----
 -------------- [queues]
                .> documents        exchange=documents(direct) key=documents
                .> classification   exchange=classification(direct) key=classification

[tasks]
  . tasks.process_document_task
  . tasks.classify_document_task
  . tasks.sync_google_drive_task
  . tasks.generate_employee_embeddings_task

[2025-01-XX XX:XX:XX,XXX: INFO/MainProcess] Connected to redis://localhost:6379/0
[2025-01-XX XX:XX:XX,XXX: INFO/MainProcess] mingle: searching for neighbors
[2025-01-XX XX:XX:XX,XXX: INFO/MainProcess] mingle: all alone
[2025-01-XX XX:XX:XX,XXX: INFO/MainProcess] celery@hostname ready.
```

### 3. Start Flask Application

In another terminal:

```bash
cd flock
python app.py
```

The application will start on `http://localhost:8080`

---

## Testing the Setup

### 1. Upload a Document

Using curl:

```bash
# Login first and get session cookie
curl -X POST http://localhost:8080/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alessa@pont-diagnostics.com","password":"123456"}' \
  -c cookies.txt

# Upload a document
curl -X POST http://localhost:8080/api/documents/upload \
  -H "Cookie: session=..." \
  -F "org_id=1" \
  -F "files=@sample.pdf"
```

Expected response:
```json
{
  "success": true,
  "uploaded": [
    {
      "doc_id": 1,
      "filename": "sample.pdf",
      "file_type": "pdf",
      "status": "pending",
      "job_id": "process_doc_1_abc123"
    }
  ],
  "failed": [],
  "message": "1 files uploaded successfully"
}
```

### 2. Check Processing Status

```bash
curl http://localhost:8080/api/jobs/process_doc_1_abc123/status \
  -H "Cookie: session=..."
```

Response:
```json
{
  "job_id": "process_doc_1_abc123",
  "status": "completed",
  "progress": 100,
  "error": null,
  "result": {
    "doc_id": 1,
    "filename": "sample.pdf",
    "chunks_created": 5,
    "extraction_method": "pypdf2",
    "char_count": 15234
  }
}
```

### 3. List Documents

```bash
curl "http://localhost:8080/api/documents?org_id=1" \
  -H "Cookie: session=..."
```

### 4. Download Document

```bash
curl "http://localhost:8080/api/documents/1/download" \
  -H "Cookie: session=..."
```

Returns presigned URL valid for 1 hour.

---

## Monitoring

### Monitor Celery Workers

```bash
# View active tasks
celery -A tasks inspect active

# View registered tasks
celery -A tasks inspect registered

# View worker stats
celery -A tasks inspect stats
```

### Monitor Redis

```bash
# Connect to Redis CLI
redis-cli

# Monitor commands in real-time
redis-cli monitor

# Check queue lengths
redis-cli llen celery

# View all keys
redis-cli keys '*'
```

### Check Logs

Celery worker logs show task execution:
```
[2025-01-XX XX:XX:XX,XXX: INFO/MainProcess] Task tasks.process_document_task[abc-123] received
[2025-01-XX XX:XX:XX,XXX: INFO/ForkPoolWorker-1] Processing document 1: sample.pdf
[2025-01-XX XX:XX:XX,XXX: INFO/ForkPoolWorker-1] Downloading file from https://...
[2025-01-XX XX:XX:XX,XXX: INFO/ForkPoolWorker-1] Extracting text from pdf file
[2025-01-XX XX:XX:XX,XXX: INFO/ForkPoolWorker-1] Storing extraction results in database
[2025-01-XX XX:XX:XX,XXX: INFO/ForkPoolWorker-1] Successfully processed document 1
[2025-01-XX XX:XX:XX,XXX: INFO/ForkPoolWorker-1] Task tasks.process_document_task[abc-123] succeeded
```

---

## Troubleshooting

### Redis Connection Error

**Error:** `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solution:**
```bash
# Check if Redis is running
redis-cli ping

# If not running, start it
brew services start redis  # macOS
sudo systemctl start redis-server  # Linux
```

### Tesseract Not Found

**Error:** `pytesseract.pytesseract.TesseractNotFound`

**Solution:**
```bash
# macOS
brew install tesseract

# Linux
sudo apt-get install tesseract-ocr

# Verify installation
tesseract --version
```

### libmagic Import Error

**Error:** `ImportError: failed to find libmagic. Check your installation`

**Solution:**
```bash
# macOS
brew install libmagic

# Linux
sudo apt-get install libmagic1 libmagic-dev

# Verify installation (should not error)
python -c "import magic; print('libmagic installed successfully')"
```

If the error persists after installing libmagic:
```bash
# Reinstall python-magic
pip uninstall python-magic
pip install python-magic
```

### DigitalOcean Spaces Upload Fails

**Error:** `botocore.exceptions.ClientError: An error occurred (403) when calling the PutObject operation: Forbidden`

**Solution:**
- Verify your `DO_SPACES_KEY` and `DO_SPACES_SECRET` are correct
- Check that the Space exists and matches `DO_SPACES_BUCKET`
- Ensure the API key has read/write permissions

### File Upload Size Limit

**Error:** `413 Request Entity Too Large`

**Solution:**
Configure nginx/gunicorn to allow larger uploads:

```nginx
# nginx.conf
client_max_body_size 50M;
```

```python
# gunicorn
gunicorn --limit-request-line 8190 --limit-request-field_size 8190 app:app
```

---

## Production Deployment

### 1. Use Supervisor for Celery

Create `/etc/supervisor/conf.d/flock-celery.conf`:

```ini
[program:flock-celery]
command=/path/to/venv/bin/celery -A tasks worker --loglevel=info
directory=/path/to/flock
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/flock/celery.log
```

Reload supervisor:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start flock-celery
```

### 2. Redis Production Configuration

Edit `/etc/redis/redis.conf`:
```
maxmemory 256mb
maxmemory-policy allkeys-lru
requirepass your_redis_password
```

Update `.env`:
```
REDIS_URL=redis://:your_redis_password@localhost:6379/0
```

### 3. Environment Variables

Set production environment variables:
```bash
export FLASK_ENV=production
export DO_SPACES_KEY=production_key
export DO_SPACES_SECRET=production_secret
export REDIS_URL=redis://...
```

---

## ✅ Sprint 2 Complete!

Sprint 2 has been successfully implemented and deployed. See [SPRINT2_DEPLOYMENT.md](SPRINT2_DEPLOYMENT.md) for production deployment instructions.

**What's New in Sprint 2:**
- Smart text chunking (1000 tokens, 200 overlap)
- OpenAI embeddings (`text-embedding-3-large`, 3072 dimensions)
- Pinecone vector database integration
- Semantic document search API (`/api/documents/search`)
- Employee semantic search API (`/api/employees/search`)
- Cost tracking and budget management
- Health check endpoints (`/health`, `/api/system/status`)
- Production-ready error handling and monitoring

## Next Steps (Sprint 3)

- Implement LLM-based document auto-classification
- Add smart folders (by team, project, date, type, person)
- Complete Google Drive sync implementation
- Add document classification API endpoints

---

## Support

For issues or questions:
- Check logs: Celery worker output, Flask logs, Redis logs
- Verify all services are running: Redis, Celery, Flask
- Check environment variables are set correctly
- Review DigitalOcean Spaces configuration

---

## API Reference

### Upload Documents
`POST /api/documents/upload`
- **Parameters:** `org_id` (form), `files` (multipart)
- **Returns:** List of uploaded documents with job IDs

### List Documents
`GET /api/documents?org_id={org_id}`
- **Returns:** Array of documents

### Get Document
`GET /api/documents/{doc_id}`
- **Returns:** Document details with metadata

### Download Document
`GET /api/documents/{doc_id}/download`
- **Returns:** Presigned URL (valid 1 hour)

### Delete Document
`DELETE /api/documents/{doc_id}`
- **Returns:** Success confirmation

### Job Status
`GET /api/jobs/{job_id}/status`
- **Returns:** Job status, progress, result
