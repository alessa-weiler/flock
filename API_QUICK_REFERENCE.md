# API Quick Reference - Sprint 2 & 3

## New Endpoints

### 🔍 Document Semantic Search

**Endpoint**: `POST /api/documents/search`

**Description**: Search documents using natural language queries

**Authentication**: Required (session cookie)

**Request**:
```json
{
  "query": "What is our hiring process?",
  "org_id": 123,
  "top_k": 10,           // optional, default 10, max 100
  "doc_type": "pdf",     // optional, filter by type
  "min_score": 0.7       // optional, default 0.7
}
```

**Response**:
```json
{
  "success": true,
  "query": "What is our hiring process?",
  "results_count": 3,
  "results": [
    {
      "doc_id": 45,
      "filename": "hiring_guide.pdf",
      "file_type": "pdf",
      "upload_date": "2025-01-15T10:30:00",
      "snippet": "Our hiring process involves three stages...",
      "score": 0.89,
      "chunk_index": 2
    }
  ]
}
```

**Example**:
```bash
curl -X POST https://pont.world/api/documents/search \
  -H "Cookie: session=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "benefits policy",
    "org_id": 1,
    "top_k": 5
  }'
```

---

### 👥 Employee Semantic Search

**Endpoint**: `POST /api/employees/search`

**Description**: Find employees by skills, expertise, or description

**Authentication**: Required

**Request**:
```json
{
  "query": "Who knows about React and TypeScript?",
  "org_id": 123,
  "top_k": 10  // optional, default 10, max 50
}
```

**Response**:
```json
{
  "success": true,
  "query": "Who knows about React and TypeScript?",
  "results_count": 2,
  "results": [
    {
      "user_id": 78,
      "name": "Jane Smith",
      "email": "jane@company.com",
      "title": "Senior Frontend Developer",
      "specialties": "React, TypeScript, Next.js",
      "bio": "10 years of experience in modern web development...",
      "experience": 10,
      "relevance_score": 0.92
    }
  ]
}
```

**Example**:
```bash
curl -X POST https://pont.world/api/employees/search \
  -H "Cookie: session=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning expert",
    "org_id": 1
  }'
```

---

### 🧠 Generate Employee Embedding

**Endpoint**: `POST /api/embeddings/generate`

**Description**: Trigger embedding generation for an employee profile

**Authentication**: Required

**Permissions**:
- Users can generate embeddings for themselves
- Owners/admins can generate for any user

**Request**:
```json
{
  "org_id": 123,
  "user_id": 456  // optional, defaults to current user
}
```

**Response**:
```json
{
  "success": true,
  "message": "Employee embedding generation started",
  "task_id": "abc-123-def",
  "user_id": 456
}
```

**Example**:
```bash
curl -X POST https://pont.world/api/embeddings/generate \
  -H "Cookie: session=YOUR_SESSION" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": 1
  }'
```

---

### 💚 Health Check

**Endpoint**: `GET /health`

**Description**: System health status for monitoring

**Authentication**: Not required (public)

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-01-20T14:23:45",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "pinecone": "healthy",
    "openai": "configured"
  }
}
```

**Status Codes**:
- `200` - Healthy or degraded
- `503` - Unhealthy

**Example**:
```bash
curl https://pont.world/health
```

---

### 📊 System Status

**Endpoint**: `GET /api/system/status`

**Description**: Detailed system metrics and statistics

**Authentication**: Required

**Response**:
```json
{
  "timestamp": "2025-01-20T14:23:45",
  "system": {
    "version": "2.0-sprint2",
    "environment": "production"
  },
  "services": {
    "database": "operational",
    "redis": "operational",
    "celery": {
      "status": "operational",
      "active_tasks": 2
    },
    "pinecone": "operational"
  },
  "statistics": {
    "documents": 1234,
    "employee_embeddings": 45,
    "jobs_24h": {
      "completed": 156,
      "failed": 2,
      "running": 1
    },
    "usage_this_month": {
      "tokens": 2500000,
      "estimated_cost": 0.325
    }
  }
}
```

**Example**:
```bash
curl https://pont.world/api/system/status \
  -H "Cookie: session=YOUR_SESSION"
```

---

## Existing Endpoints (Sprint 1)

### 📤 Upload Documents

**Endpoint**: `POST /api/documents/upload`

**Request** (multipart/form-data):
```
files: [file1.pdf, file2.docx, ...]
org_id: 123
```

**Response**:
```json
{
  "success": true,
  "uploaded": [
    {
      "doc_id": 1,
      "filename": "report.pdf",
      "file_type": "pdf",
      "status": "pending",
      "job_id": "process_doc_1_abc123"
    }
  ],
  "failed": []
}
```

---

### 📋 List Documents

**Endpoint**: `GET /api/documents?org_id=123`

**Response**:
```json
{
  "success": true,
  "documents": [
    {
      "id": 1,
      "filename": "report.pdf",
      "file_type": "pdf",
      "file_size": 524288,
      "upload_date": "2025-01-20T10:00:00",
      "processing_status": "completed"
    }
  ]
}
```

---

### 📄 Get Document Details

**Endpoint**: `GET /api/documents/1`

**Response**:
```json
{
  "success": true,
  "document": {
    "id": 1,
    "filename": "report.pdf",
    "file_type": "pdf",
    "upload_date": "2025-01-20T10:00:00",
    "processing_status": "completed",
    "metadata": {
      "page_count": 15,
      "author": "John Doe"
    }
  }
}
```

---

### 💾 Download Document

**Endpoint**: `GET /api/documents/1/download`

**Response**:
```json
{
  "success": true,
  "download_url": "https://spaces.digitalocean.com/...",
  "expires_in": 3600
}
```

---

### 🗑️ Delete Document

**Endpoint**: `DELETE /api/documents/1`

**Response**:
```json
{
  "success": true,
  "message": "Document deleted successfully"
}
```

---

### ⏳ Check Job Status

**Endpoint**: `GET /api/jobs/abc-123-def/status`

**Response**:
```json
{
  "job_id": "abc-123-def",
  "status": "completed",
  "progress": 100,
  "error": null,
  "result": {
    "doc_id": 1,
    "chunks_created": 8,
    "total_tokens": 3456,
    "embeddings_generated": 8,
    "vectors_stored": 8
  },
  "created_at": "2025-01-20T10:00:00",
  "completed_at": "2025-01-20T10:00:15"
}
```

**Job Statuses**:
- `queued` - Waiting to be processed
- `running` - Currently processing
- `completed` - Successfully completed
- `failed` - Processing failed

---

## Error Responses

All endpoints return error responses in this format:

```json
{
  "error": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes**:
- `200` - Success
- `400` - Bad request (missing/invalid parameters)
- `401` - Unauthorized (not logged in)
- `403` - Forbidden (insufficient permissions)
- `404` - Not found
- `500` - Server error

---

## Rate Limits

- **Document Search**: 100 requests/minute per user
- **Employee Search**: 100 requests/minute per user
- **Document Upload**: No limit (controlled by Celery workers)
- **Embedding Generation**: No limit (controlled by OpenAI rate limits)

---

## Best Practices

### 1. Search Queries
- Keep queries concise and specific
- Use natural language (not keywords)
- Example: ✅ "What is our vacation policy?" ❌ "vacation policy"

### 2. Top-K Selection
- Start with `top_k: 5-10` for most searches
- Increase if you need more results
- Maximum: 100 for documents, 50 for employees

### 3. Score Thresholds
- Default `min_score: 0.7` works for most cases
- Lower to 0.5-0.6 if you need more results
- Raise to 0.8-0.9 for high-precision searches

### 4. Error Handling
- Always check `success` field in response
- Handle `error` field gracefully
- Retry failed requests with exponential backoff

---

## Testing in Browser Console

```javascript
// Document search
fetch('/api/documents/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'hiring process',
    org_id: 1,
    top_k: 5
  })
})
.then(r => r.json())
.then(console.log)

// Employee search
fetch('/api/employees/search', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: 'React developer',
    org_id: 1
  })
})
.then(r => r.json())
.then(console.log)

// Health check
fetch('/health').then(r => r.json()).then(console.log)
```

---

## Sprint 3: Smart Folders & Classification

### 📁 Smart Folders API

#### Get Folders by Team

**Endpoint**: `GET /api/folders/by-team`

**Query Parameters**:
- `org_id` (required): Organization ID
- `team` (optional): Filter by specific team

**Example**:
```bash
curl "https://pont.world/api/folders/by-team?org_id=1" \
  -H "Cookie: session=YOUR_SESSION"
```

**Response**:
```json
{
  "success": true,
  "org_id": 1,
  "view_type": "by_team",
  "folders": [
    {
      "team": "Engineering",
      "document_count": 15,
      "documents": [
        {
          "id": 123,
          "filename": "api_spec.pdf",
          "file_type": "pdf",
          "upload_date": "2024-01-15T10:00:00",
          "doc_type": "technical_spec",
          "project": "API Redesign",
          "confidentiality_level": "internal",
          "tags": ["api", "design", "architecture"],
          "summary": "API architecture proposal for v2"
        }
      ]
    },
    {
      "team": "Legal",
      "document_count": 8,
      "documents": [...]
    }
  ]
}
```

**Browser Console**:
```javascript
fetch('/api/folders/by-team?org_id=1')
  .then(r => r.json())
  .then(data => {
    console.log('Teams:', data.folders.map(f => f.team));
    console.log('Total docs:', data.folders.reduce((sum, f) => sum + f.document_count, 0));
  });
```

---

#### Get Folders by Project

**Endpoint**: `GET /api/folders/by-project`

**Query Parameters**:
- `org_id` (required): Organization ID
- `project` (optional): Filter by specific project

**Example**:
```bash
curl "https://pont.world/api/folders/by-project?org_id=1&project=Website%20Redesign" \
  -H "Cookie: session=YOUR_SESSION"
```

**Response**: Same structure as team folders, with `project` instead of `team`

**Browser Console**:
```javascript
fetch('/api/folders/by-project?org_id=1')
  .then(r => r.json())
  .then(data => console.log('Projects:', data.folders));
```

---

#### Get Folders by Document Type

**Endpoint**: `GET /api/folders/by-type`

**Query Parameters**:
- `org_id` (required): Organization ID
- `doc_type` (optional): Filter by specific document type

**Supported Document Types**:
- `contract`, `policy`, `report`, `presentation`, `meeting_notes`
- `invoice`, `receipt`, `proposal`, `memo`, `email`
- `spreadsheet`, `technical_spec`, `user_manual`, `sop`
- `financial_statement`, `legal_document`, `marketing_material`
- `research_paper`, `white_paper`, `case_study`, `other`

**Example**:
```bash
curl "https://pont.world/api/folders/by-type?org_id=1&doc_type=contract" \
  -H "Cookie: session=YOUR_SESSION"
```

**Browser Console**:
```javascript
fetch('/api/folders/by-type?org_id=1')
  .then(r => r.json())
  .then(data => {
    console.table(data.folders.map(f => ({
      type: f.doc_type,
      count: f.document_count
    })));
  });
```

---

#### Get Folders by Time Period

**Endpoint**: `GET /api/folders/by-date`

**Query Parameters**:
- `org_id` (required): Organization ID
- `time_period` (optional): Filter by specific period (e.g., "2024-Q1", "2024-03")

**Time Period Formats**:
- Quarterly: `2024-Q1`, `2024-Q2`, etc.
- Monthly: `2024-01`, `2024-02`, etc.
- Yearly: `2024`, `2023`, etc.

**Example**:
```bash
curl "https://pont.world/api/folders/by-date?org_id=1&time_period=2024-Q1" \
  -H "Cookie: session=YOUR_SESSION"
```

**Browser Console**:
```javascript
fetch('/api/folders/by-date?org_id=1')
  .then(r => r.json())
  .then(data => {
    console.log('Time periods:', data.folders.map(f => f.time_period));
  });
```

---

#### Get Folders by Mentioned People

**Endpoint**: `GET /api/folders/by-person`

**Query Parameters**:
- `org_id` (required): Organization ID
- `person` (optional): Filter by specific person name

**Example**:
```bash
curl "https://pont.world/api/folders/by-person?org_id=1&person=John%20Smith" \
  -H "Cookie: session=YOUR_SESSION"
```

**Response**:
```json
{
  "success": true,
  "org_id": 1,
  "view_type": "by_person",
  "folders": [
    {
      "person": "John Smith",
      "document_count": 7,
      "documents": [...]
    },
    {
      "person": "Jane Doe",
      "document_count": 12,
      "documents": [...]
    }
  ]
}
```

**Browser Console**:
```javascript
fetch('/api/folders/by-person?org_id=1')
  .then(r => r.json())
  .then(data => {
    console.log('People mentioned:', data.folders.map(f => f.person));
  });
```

---

### 🏷️ Classification Management

#### Get Document Classification

**Endpoint**: `GET /api/documents/{doc_id}/classification`

**Description**: Retrieve full classification metadata for a document

**Example**:
```bash
curl "https://pont.world/api/documents/123/classification" \
  -H "Cookie: session=YOUR_SESSION"
```

**Response**:
```json
{
  "success": true,
  "classification": {
    "document_id": 123,
    "team": "Legal",
    "project": "Hiring",
    "doc_type": "contract",
    "time_period": "2024-Q1",
    "confidentiality_level": "confidential",
    "mentioned_people": ["John Smith", "Jane Doe"],
    "tags": ["employment", "legal", "confidential"],
    "summary": "Employment contract for John Smith as Senior Software Engineer",
    "confidence_scores": {
      "team": 0.95,
      "doc_type": 0.98,
      "project": 0.88,
      "confidentiality": 0.92
    },
    "classified_at": "2024-01-15T10:30:00Z"
  }
}
```

**Browser Console**:
```javascript
const docId = 123;
fetch(`/api/documents/${docId}/classification`)
  .then(r => r.json())
  .then(data => {
    const c = data.classification;
    console.log(`📄 ${c.doc_type} - ${c.team} - ${c.project}`);
    console.log(`🔒 ${c.confidentiality_level}`);
    console.log(`👥 ${c.mentioned_people.join(', ')}`);
    console.log(`🏷️ ${c.tags.join(', ')}`);
    console.log(`📊 Confidence: ${JSON.stringify(c.confidence_scores, null, 2)}`);
  });
```

---

#### Re-classify Document

**Endpoint**: `POST /api/documents/{doc_id}/reclassify`

**Description**: Trigger re-classification of a document using updated context

**Use Cases**:
- Manual corrections needed
- Organization context has changed (new teams, projects)
- Classification failed during initial processing
- Improve classification with more context

**Example**:
```bash
curl -X POST "https://pont.world/api/documents/123/reclassify" \
  -H "Cookie: session=YOUR_SESSION"
```

**Response**:
```json
{
  "success": true,
  "message": "Document re-classification started",
  "task_id": "abc123-def456",
  "doc_id": 123
}
```

**Browser Console**:
```javascript
const docId = 123;

// Trigger re-classification
fetch(`/api/documents/${docId}/reclassify`, { method: 'POST' })
  .then(r => r.json())
  .then(data => {
    console.log('Re-classification started:', data.task_id);

    // Wait a few seconds, then check new classification
    setTimeout(() => {
      fetch(`/api/documents/${docId}/classification`)
        .then(r => r.json())
        .then(result => {
          console.log('Updated classification:', result.classification);
        });
    }, 5000);
  });
```

---

### 🔍 Combined Smart Folder Example

**Use Case**: Build a complete document browser UI

```javascript
// Fetch all folder views for an organization
const orgId = 1;

async function loadAllFolders() {
  const [teams, projects, types, dates, people] = await Promise.all([
    fetch(`/api/folders/by-team?org_id=${orgId}`).then(r => r.json()),
    fetch(`/api/folders/by-project?org_id=${orgId}`).then(r => r.json()),
    fetch(`/api/folders/by-type?org_id=${orgId}`).then(r => r.json()),
    fetch(`/api/folders/by-date?org_id=${orgId}`).then(r => r.json()),
    fetch(`/api/folders/by-person?org_id=${orgId}`).then(r => r.json())
  ]);

  console.log('📊 Organization Document Structure:');
  console.log(`  Teams: ${teams.folders.length}`);
  console.log(`  Projects: ${projects.folders.length}`);
  console.log(`  Document types: ${types.folders.length}`);
  console.log(`  Time periods: ${dates.folders.length}`);
  console.log(`  People mentioned: ${people.folders.length}`);

  return { teams, projects, types, dates, people };
}

loadAllFolders().then(folders => {
  // Build your UI with the folder data
  console.log('Folders loaded:', folders);
});
```

---

### 📋 Bulk Re-classification Example

**Use Case**: Re-classify all documents after organizational changes

```javascript
async function reclassifyAllDocuments(orgId) {
  // Get all documents for org
  const response = await fetch(`/api/organizations/${orgId}/documents`);
  const documents = await response.json();

  console.log(`Starting re-classification of ${documents.length} documents...`);

  const results = [];
  for (const doc of documents) {
    if (doc.processing_status === 'completed') {
      const result = await fetch(`/api/documents/${doc.id}/reclassify`, {
        method: 'POST'
      }).then(r => r.json());

      results.push(result);
      console.log(`✓ Re-classifying document ${doc.id}: ${doc.filename}`);

      // Rate limit: wait 1 second between requests
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  console.log(`✓ Started re-classification for ${results.length} documents`);
  return results;
}

// Usage
reclassifyAllDocuments(1);
```

---

### 🎯 Quick Browser Console Commands

```javascript
// Quick folder summary
fetch('/api/folders/by-team?org_id=1')
  .then(r => r.json())
  .then(d => console.table(d.folders.map(f => ({ team: f.team, docs: f.document_count }))));

// Find all contracts
fetch('/api/folders/by-type?org_id=1&doc_type=contract')
  .then(r => r.json())
  .then(d => console.log('Contracts:', d.folders[0]?.documents));

// Get Q1 2024 documents
fetch('/api/folders/by-date?org_id=1&time_period=2024-Q1')
  .then(r => r.json())
  .then(d => console.log('Q1 docs:', d.folders));

// Check classification confidence
fetch('/api/documents/123/classification')
  .then(r => r.json())
  .then(d => console.log('Confidence:', d.classification.confidence_scores));
```
