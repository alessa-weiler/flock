# Sprint 2: Production Deployment Guide

## Overview

Sprint 2 adds smart text chunking, OpenAI embeddings, Pinecone vector search, and semantic search capabilities to the Knowledge Platform.

**New Features:**
- ✅ Smart text chunking with tiktoken (1000 tokens, 200 overlap)
- ✅ OpenAI embeddings (`text-embedding-3-large`, 3072 dimensions)
- ✅ Pinecone vector database integration
- ✅ Semantic document search API
- ✅ Employee semantic search API
- ✅ Cost tracking and budget management
- ✅ Health check endpoints
- ✅ Production-ready error handling

---

## Prerequisites

### Required Services

1. **PostgreSQL Database** (existing)
2. **DigitalOcean Spaces** (existing from Sprint 1)
3. **Redis** (Managed Redis recommended for production)
4. **Pinecone Account** (new for Sprint 2)
5. **OpenAI API Key** (existing)

---

## Step 1: Set Up Managed Redis (DigitalOcean)

### Create Managed Redis Database

1. Log in to [DigitalOcean](https://cloud.digitalocean.com)
2. Navigate to **Databases** → **Create Database**
3. Select **Redis** as the engine
4. Choose plan: **Basic** (1 GB RAM minimum recommended)
5. Select region: Same as your app (e.g., `lon1`)
6. Name: `flock-redis-production`
7. Click **Create Database Cluster**

### Get Connection String

1. Once created, go to **Connection Details**
2. Copy the **Connection String** (should start with `rediss://`)
3. Example: `rediss://default:password@redis-cluster.db.ondigitalocean.com:25061`

### Update Environment Variables

Add to your `.env` file (or DigitalOcean App Platform settings):

```bash
REDIS_URL=rediss://default:your_password@redis-cluster.db.ondigitalocean.com:25061
```

⚠️ **Important**: Use `rediss://` (with double 's') for SSL/TLS connection in production.

---

## Step 2: Set Up Pinecone

### Create Pinecone Account

1. Go to [pinecone.io](https://www.pinecone.io/)
2. Sign up for free account (includes 100K vectors free)
3. Verify email

### Create Pinecone Index

1. Log in to Pinecone console
2. Click **Create Index**
3. Settings:
   - **Index Name**: `flock-knowledge-base`
   - **Dimensions**: `3072` (for `text-embedding-3-large`)
   - **Metric**: `cosine`
   - **Cloud**: `AWS`
   - **Region**: `us-east-1` (or closest to your app)
   - **Plan**: Serverless (recommended)
4. Click **Create Index**

### Get API Key

1. Go to **API Keys** in Pinecone console
2. Copy your **API Key**
3. Note your **Environment** (e.g., `us-east-1`)

### Update Environment Variables

```bash
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=us-east-1
```

---

## Step 3: Update DigitalOcean App Platform

### Add Worker Component

Your app now needs TWO components:

1. **Web Service** (existing) - Runs Flask
2. **Worker Service** (new) - Runs Celery for background tasks

#### Via DigitalOcean Console:

1. Go to your App in App Platform
2. Click **Components** → **Create Component**
3. Select **Worker**
4. Settings:
   - **Name**: `worker`
   - **Source**: Same repo/branch as web service
   - **Run Command**: `celery -A tasks worker --loglevel=info --concurrency=4`
   - **Instance Size**: Basic (1GB RAM minimum)
   - **Instance Count**: 1
5. **Environment Variables**: Link same variables as web service
6. Click **Save**

#### Or update your `app.yaml`:

```yaml
name: flock
region: lon

services:
  - name: web
    github:
      repo: your-username/flock
      branch: main
    build_command: pip install -r requirements.txt
    run_command: gunicorn wsgi:application --bind 0.0.0.0:$PORT --timeout 120 --workers 2
    instance_size_slug: basic-xxs
    instance_count: 1
    http_port: 8080
    health_check:
      http_path: /health

  - name: worker
    github:
      repo: your-username/flock
      branch: main
    build_command: pip install -r requirements.txt
    run_command: celery -A tasks worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
    instance_size_slug: basic-xs
    instance_count: 1

databases:
  - name: db-postgresql
    engine: PG
    production: true

  - name: redis
    engine: REDIS
    production: true
```

### Add All Environment Variables

Ensure these are set in **App Platform → Settings → Environment Variables**:

```bash
# Existing
DATABASE_URL=postgresql://...
OPENAI_API_KEY=sk-...
DO_SPACES_KEY=...
DO_SPACES_SECRET=...
DO_SPACES_ENDPOINT=https://lon1.digitaloceanspaces.com
DO_SPACES_BUCKET=flock-documents
DO_SPACES_REGION=lon1

# New for Sprint 2
REDIS_URL=rediss://default:...@redis-cluster.db.ondigitalocean.com:25061
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=us-east-1

# Recommended
FLASK_ENV=production
```

---

## Step 4: Deploy to Production

### Option A: Git Push (Recommended)

```bash
git add .
git commit -m "Sprint 2: Add embeddings and vector search"
git push origin main
```

DigitalOcean App Platform will automatically:
1. Build new image
2. Run database migrations
3. Deploy web service
4. Deploy worker service
5. Health check passes → Go live

### Option B: Manual Deploy

1. Go to **App Platform** → Your App
2. Click **Actions** → **Force Rebuild and Deploy**
3. Monitor build logs

---

## Step 5: Verify Deployment

### 1. Check Health Endpoint

```bash
curl https://your-app.ondigitalocean.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-XX...",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "pinecone": "healthy",
    "openai": "configured"
  }
}
```

### 2. Check System Status (Authenticated)

```bash
curl https://your-app.ondigitalocean.app/api/system/status \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

Expected response:
```json
{
  "system": {
    "version": "2.0-sprint2",
    "environment": "production"
  },
  "services": {
    "database": "operational",
    "redis": "operational",
    "celery": {
      "status": "operational",
      "active_tasks": 0
    },
    "pinecone": "operational"
  },
  "statistics": {
    "documents": 0,
    "employee_embeddings": 0,
    "jobs_24h": {},
    "usage_this_month": {
      "tokens": 0,
      "estimated_cost": 0.0
    }
  }
}
```

### 3. Test Document Upload

```bash
# Upload a test document
curl -X POST https://your-app.ondigitalocean.app/api/documents/upload \
  -H "Cookie: session=..." \
  -F "files=@test.pdf" \
  -F "org_id=YOUR_ORG_ID"
```

Expected response:
```json
{
  "success": true,
  "uploaded": [
    {
      "doc_id": 1,
      "filename": "test.pdf",
      "job_id": "abc-123-def",
      "status": "pending"
    }
  ]
}
```

### 4. Check Job Progress

```bash
curl https://your-app.ondigitalocean.app/api/jobs/abc-123-def/status \
  -H "Cookie: session=..."
```

Expected response (when complete):
```json
{
  "job_id": "abc-123-def",
  "status": "completed",
  "progress": 100,
  "result": {
    "doc_id": 1,
    "chunks_created": 5,
    "total_tokens": 2450,
    "embeddings_generated": 5,
    "vectors_stored": 5
  }
}
```

### 5. Test Semantic Search

```bash
curl -X POST https://your-app.ondigitalocean.app/api/documents/search \
  -H "Cookie: session=..." \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What does this document discuss?",
    "org_id": YOUR_ORG_ID,
    "top_k": 5
  }'
```

Expected response:
```json
{
  "success": true,
  "query": "What does this document discuss?",
  "results_count": 3,
  "results": [
    {
      "doc_id": 1,
      "filename": "test.pdf",
      "snippet": "...",
      "score": 0.85,
      "chunk_index": 2
    }
  ]
}
```

---

## Step 6: Monitoring & Alerts

### Set Up Monitoring

1. **DigitalOcean Monitoring** (built-in):
   - CPU usage
   - Memory usage
   - Disk I/O
   - Network traffic

2. **Health Check Alerts**:
   - Go to **App Platform** → **Settings** → **Health Checks**
   - Path: `/health`
   - Interval: 30 seconds
   - Timeout: 10 seconds
   - Unhealthy threshold: 3 consecutive failures

3. **Cost Tracking**:
   - Monitor via `/api/system/status` endpoint
   - Check `usage_this_month.estimated_cost`
   - Set up alerts when approaching budget limit

### View Celery Worker Logs

```bash
# Via DigitalOcean Console
# App Platform → Components → worker → Runtime Logs
```

Look for:
```
✓ Generated 5 embeddings
✓ Stored 5 vectors in Pinecone
✓ Successfully processed document 1: 5 chunks, 2450 tokens
```

### View Web Service Logs

```bash
# App Platform → Components → web → Runtime Logs
```

---

## Troubleshooting

### Issue: Health check fails with "Redis unhealthy"

**Solution:**
1. Check `REDIS_URL` is correct (should use `rediss://` for SSL)
2. Verify Redis database is running in DigitalOcean
3. Check firewall rules allow connections

### Issue: "Pinecone connection failed"

**Solution:**
1. Verify `PINECONE_API_KEY` is set correctly
2. Check index name matches: `flock-knowledge-base`
3. Verify dimensions are `3072`
4. Check region/environment matches

### Issue: Worker not processing jobs

**Solution:**
1. Check worker component is running (DigitalOcean Console)
2. Verify `REDIS_URL` is same for web and worker
3. Check worker logs for errors
4. Restart worker component if needed

### Issue: "Budget limit exceeded"

**Solution:**
1. Check current usage: `GET /api/system/status`
2. Adjust budget limit in `embedding_service.py` (line ~124)
3. Or increase organization budget allowance

### Issue: Search returns no results

**Solution:**
1. Verify document processing completed successfully
2. Check Pinecone index has vectors (use Pinecone console)
3. Try lower `min_score` threshold (e.g., 0.5)
4. Verify organization namespace exists

---

## Cost Estimates

### Pinecone (Serverless)
- **Free tier**: Up to 100K vectors
- **Storage**: $0.10 per 100K vectors/month
- **Reads**: $0.02 per 1M queries

### OpenAI Embeddings
- **Model**: `text-embedding-3-large`
- **Cost**: $0.13 per 1M tokens
- **Example**: 100 documents (50 pages each) ≈ 1M tokens ≈ $0.13

### Redis (Managed)
- **Basic plan**: $15/month (1 GB RAM)
- **Includes**: SSL, automatic backups, monitoring

### Total Monthly Cost (Small Org)
- 1,000 documents: ~$5-10/month
- 10,000 documents: ~$20-30/month

---

## API Reference

### New Endpoints (Sprint 2)

#### `POST /api/documents/search`
Semantic search across documents

**Request:**
```json
{
  "query": "What is the hiring process?",
  "org_id": 123,
  "top_k": 10,
  "doc_type": "pdf",
  "min_score": 0.7
}
```

**Response:**
```json
{
  "success": true,
  "results_count": 5,
  "results": [...]
}
```

#### `POST /api/employees/search`
Semantic search for employees

**Request:**
```json
{
  "query": "Who knows about React?",
  "org_id": 123,
  "top_k": 10
}
```

#### `POST /api/embeddings/generate`
Trigger employee embedding generation

**Request:**
```json
{
  "org_id": 123,
  "user_id": 456
}
```

#### `GET /health`
Health check (public, no auth)

#### `GET /api/system/status`
System status (requires auth)

---

## Next Steps (Sprint 3)

After deploying Sprint 2, the next phase will add:
- Document auto-classification (LLM-based)
- Smart folders (by team, project, date, type)
- Google Drive sync
- Enhanced search filters

---

## Support

If you encounter issues:

1. Check logs in DigitalOcean App Platform
2. Verify all environment variables are set
3. Test health endpoint: `/health`
4. Check system status: `/api/system/status`
5. Review Celery worker logs for background task errors

For Pinecone issues, visit [docs.pinecone.io](https://docs.pinecone.io)
