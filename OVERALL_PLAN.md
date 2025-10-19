
Launch intelligent organizational knowledge platform with multi-agent chat, auto-organization, and neurologically-inspired memory

An AI-powered workspace where teams chat with all company documents and employee data. Documents auto-organize themselves, the system remembers context across conversations, and shows transparent reasoning for every answer.

## 📋 EXECUTIVE SUMMARY

**What We're Building:**
An AI-powered workspace where teams chat with all company documents and employee data. Documents auto-organize themselves, the system remembers context across conversations, and shows transparent reasoning for every answer.

**Core Innovation:**
Unlike NotebookLM (single-user, manual organization), OrgMind provides multi-user collaboration with intelligent auto-classification, three-layer memory architecture, and team-aware context.

**Target Users:**
Small to medium organizations (10-100 employees) drowning in scattered documents across Google Drive, Slack, and local files.

## 🎯 BETA OBJECTIVES

### Primary Goals:

1. Prove core value: "Chat with your company's knowledge" beats manual search
2. Validate auto-organization: Documents classify themselves accurately
3. Test memory system: AI remembers preferences and context

## 🏗️ SYSTEM ARCHITECTURE

**High-Level Components:**

`┌─────────────────────────────────────────┐
│         Frontend (React/Next.js)        │
│  • Chat Interface                       │
│  • Document Library                     │
│  • Employee Directory                   │
│  • Reasoning Display                    │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Backend API (Flask)             │
│  • Multi-Agent Orchestrator             │
│  • RAG Pipeline                         │
│  • Memory System                        │
│  • Document Processor                   │
└─────┬───────┬──────┬──────┬─────────────┘
      │       │      │      │
      ▼       ▼      ▼      ▼
  ┌────┐ ┌─────┐ ┌────┐ ┌────────┐
  │ S3 │ │Redis│ │PG  │ │Pinecone│
  └────┘ └─────┘ └────┘ └────────┘`

### Must-Have (P0)

- ✅ Document upload (PDF, DOCX, TXT, MD)
- ✅ Basic RAG implementation
- ✅ Employee profiles and onboarding
- ✅ Multi-agent chat (Orchestrator, Data Query, Research, Synthesis)
- ✅ Transparent reasoning display
- ✅ Auto-classification
- ✅ Smart folders
- ✅ Three-layer memory system
- ✅ Source citations
- ✅ Team directory
- ✅ Conversation management

### Nice-to-Have (P1)

- ⏳ Approve/reject each agent step
- ⏳ Regenerate responses
- ⏳ Thumbs up/down feedback
- ⏳ Shared conversations
- ⏳ Advanced search filters
- ⏳ Document preview in-app


I'll create a detailed plan that preserves existing therapy functionality while adding a complete document intelligence system for recruiting/non-therapy organizations.
Architecture Overview
Therapy orgs: Keep existing matching, patients view, party mode, simulation mode, networking mode
Non-therapy orgs: Keep simulation mode, networking mode, applicant screening widget; REMOVE party mode; ADD document intelligence platform with separate "Knowledge Base" tab
Phase 1: Database Schema & Infrastructure
1.1 New Database Tables
-- Documents table
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,  -- pdf, docx, txt, md, csv
    file_size INTEGER NOT NULL,  -- bytes
    storage_url TEXT NOT NULL,  -- DigitalOcean Spaces URL
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    processing_status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
    metadata_json TEXT,  -- {author, creation_date, page_count, etc}
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP
);

-- Document chunks with embeddings
CREATE TABLE document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    token_count INTEGER,
    embedding_id TEXT,  -- Pinecone vector ID
    metadata_json TEXT,  -- {page_number, section, etc}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Document classifications
CREATE TABLE document_classifications (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    team TEXT,
    project TEXT,
    doc_type TEXT,  -- contract, policy, report, presentation, etc
    time_period TEXT,  -- 2024-Q1, Jan-2024, etc
    confidentiality TEXT,  -- public, internal, confidential, restricted
    mentioned_people TEXT[],  -- array of names
    tags TEXT[],  -- array of tags
    confidence_scores_json TEXT,  -- {team: 0.95, project: 0.87, ...}
    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Employee embeddings for semantic search
CREATE TABLE employee_embeddings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    embedding_id TEXT NOT NULL,  -- Pinecone vector ID
    profile_snapshot_json TEXT,  -- snapshot of profile data used for embedding
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, organization_id)
);

-- Chat conversations
CREATE TABLE chat_conversations (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    conversation_title TEXT,  -- auto-generated from first message
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_archived BOOLEAN DEFAULT FALSE
);

-- Chat messages with reasoning
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,  -- user, assistant
    content TEXT NOT NULL,
    reasoning_json TEXT,  -- {steps: [...], agents_used: [...], execution_plan: ...}
    source_documents_json TEXT,  -- [{doc_id, snippet, page}, ...]
    source_employees_json TEXT,  -- [{user_id, name, relevance}, ...]
    source_external_json TEXT,  -- [{url, title, snippet}, ...]
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Google Drive sync
CREATE TABLE google_drive_sync (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    access_token TEXT,
    refresh_token TEXT,
    folder_id TEXT,  -- Google Drive folder to sync
    last_sync_at TIMESTAMP,
    sync_status TEXT,  -- idle, syncing, error
    sync_error TEXT,
    files_synced INTEGER DEFAULT 0,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(organization_id)
);

-- Memory store tables
CREATE TABLE memory_short_term (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    memory_json TEXT NOT NULL,  -- {messages: [...], context: {...}, entities: [...]}
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memory_mid_term (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    memory_type TEXT,  -- event, fact, pattern
    content TEXT NOT NULL,
    importance_score FLOAT DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    embedding_id TEXT,  -- Pinecone vector ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    decay_factor FLOAT DEFAULT 1.0  -- decreases over time
);

CREATE TABLE memory_long_term (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    memory_type TEXT,  -- preference, knowledge, pattern
    content TEXT NOT NULL,
    strength FLOAT DEFAULT 1.0,  -- increases with use
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP,
    embedding_id TEXT,  -- Pinecone vector ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    consolidated_from_ids INTEGER[]  -- mid-term memory IDs that formed this
);

-- Processing jobs tracking
CREATE TABLE processing_jobs (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    job_type TEXT NOT NULL,  -- document_upload, embedding_generation, classification, etc
    job_id TEXT UNIQUE NOT NULL,  -- Celery task ID
    status TEXT DEFAULT 'queued',  -- queued, running, completed, failed
    progress INTEGER DEFAULT 0,  -- 0-100
    result_json TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Usage tracking for cost management
CREATE TABLE embedding_usage (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    date DATE DEFAULT CURRENT_DATE,
    tokens_used INTEGER DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    estimated_cost FLOAT DEFAULT 0.0,
    UNIQUE(organization_id, date)
);
1.2 Dependencies Update
Add to requirements.txt:
# Vector database
pinecone-client==3.0.0

# Cloud storage
boto3==1.34.0

# Document processing
PyPDF2==3.0.1
pytesseract==0.3.10
python-docx==1.1.0
Pillow==10.2.0

# Background jobs
celery==5.3.4
redis==5.0.1

# Google Drive integration
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.116.0

# Token counting
tiktoken==0.5.2

# Perplexity API (if using external research)
# Use standard requests library

# Async support
aiohttp==3.9.1
Phase 2: File Upload & Storage (Components 1.1-1.2)
2.1 Create Storage Manager
New file: storage_manager.py
Initialize DigitalOcean Spaces client (boto3 S3-compatible)
Methods: upload_file(), download_file(), delete_file(), generate_presigned_url()
Handle file validation (type, size, naming)
Virus scanning stub (integrate ClamAV later)
2.2 Create Document Processor
New file: document_processor.py
Class DocumentExtractor with methods for each file type:
extract_pdf() - Use PyPDF2, fallback to pytesseract for scanned PDFs
extract_docx() - Use python-docx, preserve headings/lists/tables
extract_txt(), extract_md(), extract_csv()
Extract metadata: author, creation date, modification date, page count
Handle multi-column layouts and tables
Return structured data: {text: str, metadata: dict, structure: dict}
2.3 Upload API Routes
Add to app.py:
@app.route('/api/documents/upload', methods=['POST'])
@login_required
def upload_documents():
    # Validate org membership and org type (non-therapy only)
    # Support up to 10 concurrent files
    # Validate each file (type, size <= 50MB)
    # Upload to DigitalOcean Spaces
    # Create DB record with status='pending'
    # Queue Celery job for processing
    # Return job IDs and document IDs

@app.route('/api/documents/<int:doc_id>', methods=['GET'])
@login_required
def get_document(doc_id):
    # Validate org membership
    # Return document metadata + classification + processing status

@app.route('/api/documents/<int:doc_id>/download', methods=['GET'])
@login_required
def download_document(doc_id):
    # Generate presigned URL from DigitalOcean Spaces
    # Return redirect to URL

@app.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    # Soft delete (set is_deleted=True)
    # Delete from Pinecone
    # Delete from DigitalOcean Spaces
2.4 Google Drive Integration
New file: google_drive_sync.py
OAuth 2.0 flow for Google Drive authorization
Methods: authorize(), sync_folder(), list_files(), download_file()
Periodic sync (check for new/updated files)
Track last sync timestamp
Add to app.py:
@app.route('/api/gdrive/auth', methods=['POST'])
@login_required
def gdrive_auth():
    # Initiate OAuth flow
    # Return authorization URL

@app.route('/api/gdrive/callback', methods=['GET'])
@login_required
def gdrive_callback():
    # Handle OAuth callback
    # Store tokens in google_drive_sync table
    # Trigger initial sync

@app.route('/api/gdrive/sync', methods=['POST'])
@login_required
def gdrive_sync():
    # Trigger manual sync
    # Queue background job
Phase 3: Text Processing & Embeddings (Components 1.3-1.5)
3.1 Create Text Chunker
New file: text_chunker.py
class SmartChunker:
    def __init__(self, chunk_size=1000, overlap=200):
        # Use tiktoken for accurate token counting
        
    def chunk_text(self, text: str, metadata: dict) -> List[dict]:
        # Split into sentences using spaCy or NLTK
        # Group sentences into ~1000 token chunks
        # Add 200 token overlap between chunks
        # Preserve document structure context in metadata
        # Return: [{text: str, index: int, metadata: dict, tokens: int}]
3.2 Create Embedding Service
New file: embedding_service.py
class EmbeddingService:
    def __init__(self):
        self.client = OpenAI()
        self.model = "text-embedding-3-large"
        
    def generate_embeddings(self, texts: List[str], org_id: int) -> List[List[float]]:
        # Batch up to 100 texts per API call
        # Rate limiting: max 3000 RPM
        # Track tokens used
        # Update embedding_usage table
        # Return embeddings
        
    def track_usage(self, org_id: int, tokens: int):
        # Log to embedding_usage table
        # Calculate cost ($0.00013 per 1K tokens)
        # Check if approaching budget limit
        # Send alert if needed
3.3 Vector Store Setup
New file: vector_store.py
class VectorStore:
    def __init__(self):
        self.pinecone = pinecone.Pinecone(api_key=PINECONE_API_KEY)
        self.index_name = "flock-knowledge-base"
        
    def upsert_document_chunks(self, org_id: int, chunks: List[dict]):
        # Namespace: f"org_{org_id}"
        # Vector IDs: f"doc_{doc_id}_chunk_{chunk_idx}"
        # Metadata: {doc_id, chunk_index, text, filename, doc_type, team, project, ...}
        # Batch upsert (100 vectors at a time)
        
    def upsert_employee_embedding(self, org_id: int, user_id: int, embedding: List[float], metadata: dict):
        # Vector ID: f"employee_{user_id}"
        # Metadata: {user_id, name, title, department, skills, bio, ...}
        
    def search(self, org_id: int, query_embedding: List[float], top_k: int = 10, filters: dict = None):
        # Search in namespace f"org_{org_id}"
        # Apply metadata filters if provided
        # Return matches with scores and metadata
        
    def delete_document(self, org_id: int, doc_id: int):
        # Delete all vectors matching doc_id in namespace
Phase 4: Background Job Processing (Component 1.8)
4.1 Celery Configuration
New file: celery_config.py
from celery import Celery

celery_app = Celery('flock',
                    broker='redis://localhost:6379/0',
                    backend='redis://localhost:6379/0')

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
)
4.2 Background Tasks
New file: tasks.py
from celery_config import celery_app
from document_processor import DocumentExtractor
from text_chunker import SmartChunker
from embedding_service import EmbeddingService
from vector_store import VectorStore

@celery_app.task(bind=True)
def process_document_task(self, doc_id: int, org_id: int):
    # Update job status to 'running'
    # Download file from DigitalOcean Spaces
    # Extract text and metadata
    # Chunk text
    # Generate embeddings
    # Store in Pinecone
    # Classify document (call classify_document_task)
    # Update progress throughout
    # Update document status to 'completed'
    # Handle errors and retries
    
@celery_app.task(bind=True)
def classify_document_task(self, doc_id: int):
    # Retrieve document chunks
    # Use LLM to classify (Team, Project, Type, Time Period, Confidentiality)
    # Extract mentioned people and entities
    # Generate tags
    # Store in document_classifications table
    
@celery_app.task
def sync_google_drive_task(org_id: int):
    # Get Google Drive config
    # List files in folder since last_sync
    # Download new/updated files
    # Trigger process_document_task for each
    # Update last_sync_at
    
@celery_app.task
def generate_employee_embeddings_task(org_id: int, user_id: int):
    # Get employee profile data
    # Create text representation
    # Generate embedding
    # Store in Pinecone and employee_embeddings table
    
@celery_app.task
def consolidate_memories_task():
    # Run nightly
    # Find mid-term memories older than 7 days with high importance
    # Cluster related memories
    # Consolidate to long-term storage
    # Update decay_factor for remaining mid-term memories
    # Delete weak memories (low importance + high decay)
4.3 Job Status API
Add to app.py:
@app.route('/api/jobs/<job_id>/status', methods=['GET'])
@login_required
def get_job_status(job_id):
    # Query processing_jobs table
    # Return {status, progress, result, error}
Phase 5: Auto-Classification & Smart Folders (Components 1.6-1.7)
5.1 Document Classifier
New file: document_classifier.py
class DocumentClassifier:
    def __init__(self):
        self.client = OpenAI()
        
    def classify(self, document_text: str, filename: str, org_context: dict) -> dict:
        # Build prompt with org context (teams, common projects, etc)
        # Ask LLM to classify:
        #   - Team (e.g., Engineering, Marketing, Sales)
        #   - Project (e.g., Q1 Launch, Rebrand 2024)
        #   - Type (contract, policy, report, presentation, meeting notes, etc)
        #   - Time Period (2024-Q1, Jan-2024, FY2024)
        #   - Confidentiality (public, internal, confidential, restricted)
        # Extract mentioned people (full names)
        # Suggest 3-5 tags
        # Return confidence scores for each classification
        # Return: {team, project, doc_type, time_period, confidentiality, 
        #          mentioned_people: [], tags: [], confidence_scores: {}}
5.2 Smart Folders API
Add to app.py:
@app.route('/api/folders/<org_id>/<view_type>', methods=['GET'])
@login_required
def get_smart_folders(org_id, view_type):
    # view_type: team, date, project, type, person
    # Query document_classifications
    # Group documents by view_type
    # Return folder structure with counts
    # Example: {folders: [{name: "Engineering", count: 45, doc_ids: [...]}, ...]}

@app.route('/api/folders/<org_id>/documents', methods=['POST'])
@login_required
def get_documents_by_filter():
    # Request body: {filters: {team: "Engineering", project: "Q1 Launch"}}
    # Query documents matching ALL filters
    # Support multi-folder membership
    # Return document list with metadata
Phase 6: Memory System (Components 3.1-3.5)
6.1 Memory Manager
New file: memory_system.py
class MemorySystem:
    def __init__(self, redis_client, pg_connection, vector_store):
        self.redis = redis_client
        self.db = pg_connection
        self.vectors = vector_store
        
    # SHORT-TERM MEMORY (Redis)
    def store_short_term(self, conversation_id: int, messages: List[dict], context: dict):
        # Store last 10 messages in Redis
        # Key: f"conversation:{conversation_id}:short_term"
        # Expire after 1 hour
        
    def get_short_term(self, conversation_id: int):
        # Retrieve from Redis
        
    # MID-TERM MEMORY
    def store_mid_term(self, org_id: int, user_id: int, memory_type: str, content: str, importance: float):
        # Insert into memory_mid_term table
        # Generate embedding and store in Pinecone
        # Set decay_factor = 1.0
        
    def retrieve_mid_term(self, org_id: int, query_embedding: List[float], days_back: int = 30):
        # Search Pinecone for relevant mid-term memories
        # Apply time filter (created_at within days_back)
        # Apply decay factor to relevance scores
        # Increment access_count
        
    # LONG-TERM MEMORY
    def store_long_term(self, org_id: int, user_id: int, memory_type: str, content: str):
        # Insert into memory_long_term table
        # Generate embedding and store in Pinecone
        # Set strength = 1.0
        
    def retrieve_long_term(self, org_id: int, query_embedding: List[float]):
        # Search Pinecone for relevant long-term memories
        # Boost scores by strength factor
        # Increment access_count and strength
        # Update last_accessed
        
    # MULTI-STAGE RETRIEVAL
    def retrieve_context(self, conversation_id: int, org_id: int, user_id: int, query: str):
        # Generate query embedding
        # 1. Get short-term from Redis
        # 2. Search mid-term memories
        # 3. Search long-term memories
        # 4. Search documents (via vector_store)
        # 5. Search employee profiles
        # Combine and rank by relevance with decay/strength factors
        # Return unified context
        
    # CONSOLIDATION
    def consolidate_memories(self, org_id: int):
        # Find mid-term memories older than 7 days with importance > 0.7
        # Cluster similar memories using embeddings
        # Create consolidated long-term memory
        # Update decay_factor for remaining mid-term
        # Delete memories with decay_factor < 0.2 and importance < 0.3
6.2 Memory Consolidation Job
Already included in tasks.py - runs nightly via Celery Beat
Phase 7: Multi-Agent Chat System (Components 4.1-4.4)
7.1 Chat Agents
New file: chat_agents.py
class MasterOrchestrator:
    def __init__(self, memory_system, vector_store, embedding_service):
        self.memory = memory_system
        self.vectors = vector_store
        self.embeddings = embedding_service
        self.data_agent = DataQueryAgent(vector_store, embedding_service)
        self.research_agent = ResearchAgent()
        self.synthesis_agent = SynthesisAgent()
        
    def process_query(self, conversation_id: int, org_id: int, user_id: int, query: str):
        # 1. Retrieve context from memory system
        # 2. Analyze query and create execution plan
        # 3. Determine which agents to use
        # 4. Execute agents in parallel/sequence
        # 5. Collect results
        # 6. Synthesize final answer
        # 7. Store in chat_messages with reasoning_json
        # 8. Update memories
        # Return: {answer, reasoning_steps, sources}

class DataQueryAgent:
    def __init__(self, vector_store, embedding_service):
        self.vectors = vector_store
        self.embeddings = embedding_service
        
    def search_documents(self, org_id: int, query: str, filters: dict = None):
        # Generate query embedding
        # Search Pinecone for relevant document chunks
        # Return: [{doc_id, chunk_text, filename, page, score}, ...]
        
    def search_employees(self, org_id: int, query: str):
        # Generate query embedding
        # Search employee embeddings
        # Return: [{user_id, name, title, relevance, skills}, ...]
        
    def hybrid_search(self, org_id: int, query: str):
        # Combine vector search + keyword search
        # Re-rank results
        # Return unified results

class ResearchAgent:
    def __init__(self):
        self.perplexity_api_key = os.environ.get('PERPLEXITY_API_KEY')
        
    def query_external(self, query: str):
        # Call Perplexity API
        # Parse results
        # Return: [{url, title, snippet, relevance}, ...]

class SynthesisAgent:
    def __init__(self):
        self.client = OpenAI()
        
    def synthesize(self, query: str, doc_results: List, employee_results: List, 
                   external_results: List, context: dict):
        # Combine all sources
        # Generate coherent answer with GPT-4
        # Maintain attribution to sources
        # Resolve contradictions
        # Return: {answer, confidence, sources_used}
7.2 RAG Pipeline
New file: rag_pipeline.py
class RAGPipeline:
    def __init__(self, vector_store, embedding_service, memory_system):
        self.vectors = vector_store
        self.embeddings = embedding_service
        self.memory = memory_system
        
    def retrieve(self, org_id: int, query: str, top_k: int = 10):
        # Generate query embedding
        # Search documents
        # Retrieve relevant chunks
        # Re-rank by relevance
        # Return top_k results
        
    def augment(self, query: str, retrieved_chunks: List, context: dict):
        # Build augmented prompt
        # Include retrieved chunks
        # Include conversation context
        # Include relevant memories
        
    def generate(self, augmented_prompt: str):
        # Call GPT-4 with augmented context
        # Stream response
        # Track reasoning steps
        # Return answer with citations
7.3 Chat API Routes
Add to app.py:
@app.route('/api/chat/conversations', methods=['GET'])
@login_required
def get_conversations():
    # List all conversations for user in org
    # Order by last_message_at DESC
    # Return: [{id, title, last_message_preview, last_message_at}, ...]

@app.route('/api/chat/conversations', methods=['POST'])
@login_required
def create_conversation():
    # Create new conversation
    # Return conversation_id

@app.route('/api/chat/<int:conversation_id>/messages', methods=['GET'])
@login_required
def get_messages(conversation_id):
    # Retrieve all messages in conversation
    # Return with reasoning and sources

@app.route('/api/chat/<int:conversation_id>/messages', methods=['POST'])
@login_required
def send_message(conversation_id):
    # Get user message from request body
    # Call MasterOrchestrator.process_query()
    # Stream response back (Server-Sent Events or WebSocket)
    # Store both user message and assistant response
    # Update conversation.last_message_at
    
@app.route('/api/chat/<int:conversation_id>/archive', methods=['POST'])
@login_required
def archive_conversation(conversation_id):
    # Set is_archived = True
Phase 8: Employee Directory & Embeddings (Components 2.1-2.2)
8.1 Employee Embedding Generation
Add to existing employee profile update logic:
# When employee profile is created/updated, trigger embedding generation
generate_employee_embeddings_task.delay(org_id, user_id)
8.2 Employee Directory API
Add to app.py:
@app.route('/api/employees/<int:org_id>', methods=['GET'])
@login_required
def get_employees(org_id):
    # Query all members of organization
    # Support filters: department, team
    # Support sorting: name, title
    # Return employee list

@app.route('/api/employees/<int:org_id>/search', methods=['POST'])
@login_required
def search_employees(org_id):
    # Request body: {query: "Who knows about machine learning?"}
    # Generate query embedding
    # Search employee_embeddings in Pinecone
    # Return ranked employees with relevance scores
    
@app.route('/api/employees/<int:user_id>/knowledge', methods=['GET'])
@login_required
def get_employee_knowledge(user_id):
    # Find all documents where user is mentioned
    # Find all documents uploaded by user
    # Return knowledge graph data
Phase 9: UI Components (Component 5.x)
9.1 Update Organization View Logic
Modify in app.py at line ~10694:
@app.route('/organization/<int:org_id>')
@login_required
def organization_view(org_id):
    # ... existing logic to get org_info ...
    
    use_case = org_info.get('use_case', 'hiring')
    
    if use_case == 'therapy_matching':
        # Render existing therapy organization view
        return render_therapy_organization_view(org_info, members, simulations, user_info)
    else:
        # Render knowledge platform view for recruiting/non-therapy orgs
        return render_knowledge_platform_view(org_info, members, user_info)
9.2 Knowledge Platform UI Template
Add new function in app.py:
def render_knowledge_platform_view(org_info: Dict, members: List[Dict], user_info: Dict) -> str:
    """Render knowledge platform for non-therapy organizations"""
    
    org_id = org_info['id']
    org_name = org_info['name']
    is_owner = any(m['user_id'] == user_info['id'] and m['role'] == 'owner' for m in members)
    
    # Tabs: Employees, Simulations, Knowledge Base
    # Remove party mode entirely
    # Keep simulation mode and networking mode for employee screening
    
    content = f'''
    <style>
        /* Tab styles */
        .knowledge-tabs {{
            display: flex;
            gap: 1rem;
            border-bottom: 2px solid #e0e0e0;
            margin-bottom: 2rem;
        }}
        .knowledge-tab {{
            padding: 1rem 2rem;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 1rem;
            color: #666;
            transition: all 0.3s;
        }}
        .knowledge-tab.active {{
            color: #000;
            border-bottom: 3px solid #000;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        
        /* Document library styles */
        .upload-zone {{
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 3rem;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }}
        .upload-zone:hover {{
            border-color: #000;
            background: #f9f9f9;
        }}
        .doc-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1.5rem;
            margin-top: 2rem;
        }}
        .doc-card {{
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 1.5rem;
            cursor: pointer;
            transition: all 0.3s;
        }}
        .doc-card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.75rem;
            background: #f0f0f0;
            margin-right: 0.5rem;
        }}
        
        /* Chat interface styles */
        .chat-container {{
            display: grid;
            grid-template-columns: 300px 1fr;
            gap: 1rem;
            height: calc(100vh - 200px);
        }}
        .chat-sidebar {{
            border-right: 1px solid #e0e0e0;
            overflow-y: auto;
        }}
        .conversation-item {{
            padding: 1rem;
            cursor: pointer;
            border-bottom: 1px solid #f0f0f0;
        }}
        .conversation-item:hover {{
            background: #f9f9f9;
        }}
        .chat-main {{
            display: flex;
            flex-direction: column;
        }}
        .messages-area {{
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
        }}
        .message {{
            margin-bottom: 1.5rem;
        }}
        .message.user {{
            background: #f0f0f0;
            padding: 1rem;
            border-radius: 8px;
            max-width: 70%;
        }}
        .message.assistant {{
            padding: 1rem;
            border-left: 3px solid #000;
            max-width: 80%;
        }}
        .reasoning-display {{
            background: #f9f9f9;
            padding: 1rem;
            border-radius: 8px;
            margin-top: 0.5rem;
            font-size: 0.9rem;
            color: #666;
        }}
        .reasoning-step {{
            padding: 0.5rem 0;
            border-bottom: 1px solid #e0e0e0;
        }}
        .source-citations {{
            margin-top: 1rem;
            padding: 1rem;
            background: #fafafa;
            border-radius: 8px;
        }}
        .source-item {{
            padding: 0.5rem;
            margin: 0.5rem 0;
            border-left: 2px solid #ccc;
            padding-left: 1rem;
        }}
        .message-input-area {{
            border-top: 1px solid #e0e0e0;
            padding: 1rem;
        }}
        .message-input {{
            width: 100%;
            min-height: 80px;
            padding: 1rem;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            resize: vertical;
        }}
    </style>
    
    <div class="knowledge-platform">
        <h1>{org_name}</h1>
        
        <div class="knowledge-tabs">
            <button class="knowledge-tab active" onclick="switchTab('employees')">
                Employees & Screening
            </button>
            <button class="knowledge-tab" onclick="switchTab('knowledge')">
                Knowledge Base
            </button>
            {"<button class='knowledge-tab' onclick='switchTab(\"settings\")'>Settings</button>" if is_owner else ""}
        </div>
        
        <!-- EMPLOYEES TAB -->
        <div id="employees-tab" class="tab-content active">
            <h2>Team Members</h2>
            <div class="employee-directory">
                <!-- Employee cards here -->
            </div>
            
            <h2>Applicant Screening</h2>
            <p>Use the embedded widget to screen new candidates and run simulations</p>
            <div class="screening-modes">
                <button class="mode-btn" onclick="switchMode('simulation')">Simulation Mode</button>
                <button class="mode-btn" onclick="switchMode('networking')">Networking Mode</button>
                <!-- NO PARTY MODE -->
            </div>
            <div id="screening-embed-container"></div>
        </div>
        
        <!-- KNOWLEDGE BASE TAB -->
        <div id="knowledge-tab" class="tab-content">
            <div class="kb-layout">
                <div class="kb-sidebar">
                    <h3>Smart Folders</h3>
                    <select id="folder-view" onchange="loadFolderView()">
                        <option value="team">By Team</option>
                        <option value="date">By Date</option>
                        <option value="project">By Project</option>
                        <option value="type">By Type</option>
                        <option value="person">By Person</option>
                    </select>
                    <div id="folder-tree"></div>
                </div>
                
                <div class="kb-main">
                    <div class="kb-tabs">
                        <button class="kb-tab active" onclick="switchKBTab('documents')">Documents</button>
                        <button class="kb-tab" onclick="switchKBTab('chat')">Ask Questions</button>
                    </div>
                    
                    <!-- DOCUMENTS VIEW -->
                    <div id="documents-view" class="kb-tab-content active">
                        <div class="upload-zone" onclick="document.getElementById('file-upload').click()">
                            <input type="file" id="file-upload" multiple style="display:none" 
                                   accept=".pdf,.docx,.txt,.md,.csv" 
                                   onchange="handleFileUpload(event)">
                            <h3>Drop files here or click to upload</h3>
                            <p>Supported: PDF, DOCX, TXT, MD, CSV (Max 50MB, up to 10 files)</p>
                        </div>
                        
                        <div class="gdrive-sync">
                            <button onclick="syncGoogleDrive()">Sync Google Drive</button>
                        </div>
                        
                        <div class="doc-controls">
                            <input type="text" id="doc-search" placeholder="Search documents..." 
                                   oninput="searchDocuments()">
                            <select id="doc-sort" onchange="sortDocuments()">
                                <option value="date_desc">Newest First</option>
                                <option value="date_asc">Oldest First</option>
                                <option value="name">Name A-Z</option>
                            </select>
                        </div>
                        
                        <div id="doc-grid" class="doc-grid">
                            <!-- Document cards populated via JS -->
                        </div>
                    </div>
                    
                    <!-- CHAT VIEW -->
                    <div id="chat-view" class="kb-tab-content">
                        <div class="chat-container">
                            <div class="chat-sidebar">
                                <button onclick="createNewConversation()">+ New Conversation</button>
                                <div id="conversations-list">
                                    <!-- Conversation items populated via JS -->
                                </div>
                            </div>
                            
                            <div class="chat-main">
                                <div class="messages-area" id="messages-area">
                                    <div class="empty-state">
                                        <h3>Ask a question about your documents or team</h3>
                                        <p>Examples:</p>
                                        <ul>
                                            <li>"What are our main hiring priorities for Q2?"</li>
                                            <li>"Who knows about TypeScript on the team?"</li>
                                            <li>"Summarize the Q1 marketing report"</li>
                                        </ul>
                                    </div>
                                </div>
                                
                                <div class="message-input-area">
                                    <textarea id="message-input" class="message-input" 
                                              placeholder="Ask a question..."
                                              onkeydown="handleMessageKeydown(event)"></textarea>
                                    <button onclick="sendMessage()">Send</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- SETTINGS TAB (owners only) -->
        {"<div id='settings-tab' class='tab-content'>" + render_kb_settings(org_id) + "</div>" if is_owner else ""}
    </div>
    
    <script>
        // Tab switching
        function switchTab(tabName) {{
            document.querySelectorAll('.knowledge-tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tabName + '-tab').classList.add('active');
        }}
        
        function switchKBTab(tabName) {{
            document.querySelectorAll('.kb-tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.kb-tab-content').forEach(content => content.classList.remove('active'));
            event.target.classList.add('active');
            document.getElementById(tabName + '-view').classList.add('active');
        }}
        
        // File upload handling
        async function handleFileUpload(event) {{
            const files = Array.from(event.target.files);
            if (files.length > 10) {{
                alert('Maximum 10 files at once');
                return;
            }}
            
            const formData = new FormData();
            files.forEach(file => {{
                if (file.size > 50 * 1024 * 1024) {{
                    alert(`${{file.name}} exceeds 50MB limit`);
                    return;
                }}
                formData.append('files', file);
            }});
            
            try {{
                const response = await fetch('/api/documents/upload?org_id={org_id}', {{
                    method: 'POST',
                    body: formData
                }});
                const result = await response.json();
                
                // Show upload progress
                result.jobs.forEach(job => trackJobProgress(job.job_id));
                
                // Refresh documents view
                loadDocuments();
            }} catch (error) {{
                console.error('Upload failed:', error);
                alert('Upload failed');
            }}
        }}
        
        // Chat functionality
        let currentConversationId = null;
        
        async function sendMessage() {{
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            if (!message) return;
            
            // Add user message to UI
            appendMessage('user', message);
            input.value = '';
            
            // Show loading state
            const loadingDiv = appendMessage('assistant', 'Thinking...');
            
            try {{
                const response = await fetch(`/api/chat/${{currentConversationId}}/messages`, {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message, org_id: {org_id}}})
                }});
                
                const data = await response.json();
                
                // Replace loading message with actual response
                loadingDiv.remove();
                appendMessage('assistant', data.answer, data.reasoning, data.sources);
                
            }} catch (error) {{
                console.error('Message failed:', error);
                loadingDiv.textContent = 'Error processing message';
            }}
        }}
        
        function appendMessage(role, content, reasoning = null, sources = null) {{
            const messagesArea = document.getElementById('messages-area');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${{role}}`;
            messageDiv.innerHTML = `
                <div class="message-content">${{content}}</div>
                ${{reasoning ? renderReasoning(reasoning) : ''}}
                ${{sources ? renderSources(sources) : ''}}
            `;
            messagesArea.appendChild(messageDiv);
            messagesArea.scrollTop = messagesArea.scrollHeight;
            return messageDiv;
        }}
        
        function renderReasoning(reasoning) {{
            return `
                <div class="reasoning-display">
                    <strong>How I figured this out:</strong>
                    ${{reasoning.steps.map(step => `
                        <div class="reasoning-step">
                            <span class="step-icon">✓</span> ${{step}}
                        </div>
                    `).join('')}}
                </div>
            `;
        }}
        
        function renderSources(sources) {{
            if (!sources.documents && !sources.employees && !sources.external) return '';
            
            let html = '<div class="source-citations"><strong>Sources:</strong>';
            
            if (sources.documents) {{
                html += '<div class="source-section"><em>Documents:</em>';
                sources.documents.forEach(doc => {{
                    html += `<div class="source-item">${{doc.filename}} (Page ${{doc.page}})</div>`;
                }});
                html += '</div>';
            }}
            
            if (sources.employees) {{
                html += '<div class="source-section"><em>Team Members:</em>';
                sources.employees.forEach(emp => {{
                    html += `<div class="source-item">${{emp.name}} - ${{emp.title}}</div>`;
                }});
                html += '</div>';
            }}
            
            if (sources.external) {{
                html += '<div class="source-section"><em>External Sources:</em>';
                sources.external.forEach(ext => {{
                    html += `<div class="source-item"><a href="${{ext.url}}" target="_blank">${{ext.title}}</a></div>`;
                }});
                html += '</div>';
            }}
            
            html += '</div>';
            return html;
        }}
        
        // Initialize
        loadDocuments();
        loadConversations();
    </script>
    '''
    
    return render_template_with_header(f"{org_name} - Knowledge Platform", content)
9.3 Remove Party Mode for Non-Therapy Orgs
Modify embed configuration check in app.py:
@app.route('/organization/<int:org_id>/embed-settings', methods=['GET', 'POST'])
@login_required
def organization_embed_settings(org_id):
    # ... existing logic ...
    
    use_case = org_info.get('use_case', 'hiring')
    is_therapy = use_case == 'therapy_matching'
    
    # For non-therapy orgs, only allow 'simulation' mode
    # For therapy orgs, allow both 'party' and 'simulation'
    available_modes = ['party', 'simulation'] if is_therapy else ['simulation']
    
    # Update UI to only show available modes
    # ...
Phase 10: Integration & Final Touches
10.1 Update Organization Creation
Modify in app.py at line ~7365:
@app.route('/create-organization', methods=['GET', 'POST'])
@login_required
def create_organization():
    # ... existing logic ...
    
    # In the form HTML, update use_case options:
    '''
    <select name="use_case" required>
        <option value="therapy_matching">Therapy Practice Matching</option>
        <option value="recruiting_knowledge">Recruiting & Knowledge Platform</option>
    </select>
    '''
    
    # When creating org, if use_case is 'recruiting_knowledge':
    # - Initialize Pinecone namespace
    # - Create default folders
    # - Generate employee embeddings for creator
10.2 Cost Tracking Dashboard
Add route:
@app.route('/api/organization/<int:org_id>/usage', methods=['GET'])
@login_required
def get_usage_stats(org_id):
    # Query embedding_usage table
    # Return: {
    #   current_month: {tokens, cost, api_calls},
    #   trend: [...],
    #   budget_limit: X,
    #   alert_threshold: Y
    # }
10.3 Admin Controls
Add to settings tab:
Set monthly embedding budget limit
Configure Google Drive sync schedule
Manage document retention policies
View processing job history
Implementation Order Summary
Sprint 1: Foundation (Week 1-2)
Database schema setup
DigitalOcean Spaces integration
File upload API
Document processor (PDF, DOCX, TXT, MD, CSV extraction)
Basic Celery setup
Sprint 2: Embeddings & Vector Store (Week 2-3)
Text chunking system
Embedding service with OpenAI
Pinecone integration
Background job processing
Job status tracking
Sprint 3: Classification & Folders (Week 3-4)
Document classifier
Smart folder system
Google Drive sync
Employee embeddings
Sprint 4: Memory System (Week 4-5)
Short-term memory (Redis)
Mid-term memory (PostgreSQL + Pinecone)
Long-term memory
Memory consolidation job
Multi-stage retrieval
Sprint 5: Chat & Agents (Week 5-6)
Master orchestrator
Data query agent
Research agent (optional Perplexity)
Synthesis agent
RAG pipeline
Chat API
Sprint 6: UI/UX (Week 6-7)
Knowledge platform view
Document library UI
Chat interface
Reasoning display
Source citations
Employee directory
Smart folder browser
Sprint 7: Integration & Polish (Week 7-8)
Update organization creation flow
Remove party mode for non-therapy orgs
Cost tracking
Usage dashboards
Testing & bug fixes
Documentation
This plan maintains all existing therapy functionality while adding a comprehensive knowledge platform for non-therapy organizations. The key differentiator is the use_case field in the organizations table, which routes to the appropriate UI and features.