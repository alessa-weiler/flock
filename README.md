# Flock

> AI-powered professional networking and organizational knowledge management platform

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Flask 2.3+](https://img.shields.io/badge/flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-orange.svg)](https://openai.com/)

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

---

## Overview

**Flock** is a sophisticated AI-powered platform that combines professional networking with organizational knowledge management. It leverages advanced psychological profiling, vector-based semantic search, and retrieval-augmented generation (RAG) to create meaningful connections and provide intelligent access to organizational knowledge.

### What Problems Does Flock Solve?

1. **Intelligent Networking**: Moves beyond surface-level matching to deep personality compatibility
2. **Knowledge Discovery**: Makes organizational documents searchable and queryable through natural language
3. **Professional Development**: Provides AI-driven insights based on LinkedIn profiles and career trajectories
4. **Document Management**: Automatically processes, classifies, and indexes documents for semantic search
5. **Subscription Management**: Built-in payment processing and tier-based access control

---

## Key Features

###  **Intelligent Matching & Profiling**
- **Psychological Profiling**: 10-step comprehensive onboarding process capturing:
  - Values, risk tolerance, and decision-making patterns
  - Conflict resolution styles and relationship priorities
  - Future orientation and moral frameworks
  - Social identity and institutional trust
- **AI-Powered Enrichment**: Integrates LinkedIn data via web scraping for professional context
- **Voice & Text Input**: Flexible data capture with OpenAI Whisper transcription
- **Personality Synthesis**: GPT-4 generates comprehensive psychological profiles

###  **RAG-Powered Knowledge Base**
- **Document Processing**: Supports PDF, DOCX, TXT, MD, CSV with OCR for scanned documents
- **Vector Search**: Pinecone-based semantic search with 3072-dimensional embeddings
- **Intelligent Chunking**: Context-aware text splitting with token limits
- **Citation-Based Answers**: GPT-4 provides answers with document source attribution
- **Multi-Tenant**: Namespace-based organization isolation

###  **Subscription & Payment**
- **Stripe Integration**: Secure payment processing with webhook support
- **Tiered Access**: Free tier (20 simulations) and unlimited subscription
- **Usage Tracking**: Comprehensive analytics for API costs and embeddings
- **Budget Management**: Configurable spending limits per organization

###  **Security & Privacy**
- **User Authentication**: Secure session management with encrypted passwords
- **Data Encryption**: Field-level encryption for sensitive profile data
- **Block Lists**: User-defined exclusions for privacy control
- **Organization Isolation**: Multi-tenant data separation

### ⚡ **Background Processing**
- **Celery Workers**: Asynchronous document processing and embeddings
- **Redis Queue**: Task management and caching
- **Rate Limiting**: API throttling with exponential backoff
- **Circuit Breaker**: Fault tolerance for external API failures

---

## Tech Stack

### Backend
- **Framework**: Flask 2.3.3
- **Database**: PostgreSQL (via psycopg2-binary)
- **Task Queue**: Celery 5.3.4 + Redis 5.0.1
- **WSGI Server**: Gunicorn 21.2.0

### AI & ML
- **Language Models**: OpenAI GPT-4, GPT-4o (via openai==1.100.2)
- **Embeddings**: text-embedding-3-large (3072 dimensions)
- **Speech-to-Text**: OpenAI Whisper API
- **Vector Database**: Pinecone 3.0.0

### Document Processing
- **PDF**: PyPDF2 3.0.1, pdf2image 1.17.0
- **OCR**: pytesseract 0.3.10
- **Word**: python-docx 1.1.0
- **Images**: Pillow 10.2.0
- **File Type Detection**: python-magic 0.4.27

### Cloud Services
- **Storage**: AWS S3 (boto3 1.34.0)
- **Payments**: Stripe 5.0.0+
- **LinkedIn Data**: Fresh API integration

### Security
- **Encryption**: cryptography 41.0.4
- **Password Hashing**: Werkzeug 2.3.7
- **Environment Variables**: python-dotenv 1.0.0

### Utilities
- **HTTP**: requests 2.31.0, aiohttp 3.9.1
- **Token Counting**: tiktoken 0.5.2
- **Google APIs**: google-auth, google-api-python-client

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│          (Flask Templates + JavaScript)                      │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                     Flask Application                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Auth       │  │  Onboarding  │  │   Payment    │      │
│  │   System     │  │   Flow       │  │   Manager    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   RAG        │  │   Document   │  │   Vector     │      │
│  │   Pipeline   │  │   Processor  │  │   Store      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼───────┐ ┌────▼─────┐ ┌──────▼──────┐
│  PostgreSQL   │ │  Redis   │ │   Celery    │
│  (User Data)  │ │ (Cache)  │ │  (Workers)  │
└───────────────┘ └──────────┘ └─────────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼────────┐ ┌───▼──────┐ ┌─────▼──────┐
│   OpenAI API   │ │ Pinecone │ │  Stripe    │
│ (GPT-4/Whisper)│ │ (Vectors)│ │ (Payment)  │
└────────────────┘ └──────────┘ └────────────┘
```

### Data Flow

#### 1. User Onboarding
```
User Input → Voice/Text Capture → OpenAI Whisper (if voice)
    → Profile Storage → LinkedIn Scraping → AI Enrichment
    → Psychological Profile Generation
```

#### 2. Document Processing
```
Upload → S3 Storage → Celery Task → Document Extraction
    → Text Chunking → Embedding Generation → Pinecone Upsert
```

#### 3. RAG Query
```
User Question → Query Embedding → Vector Search (Pinecone)
    → Context Assembly → GPT-4 Generation → Cited Answer
```

---

## Prerequisites

### System Requirements
- Python 3.9 or higher
- PostgreSQL 13+ (or DigitalOcean Managed Database)
- Redis 6+ (or managed Redis service)
- 2GB+ RAM recommended
- Storage for documents (local or S3)

### External Services
- **OpenAI API** account with API key
- **Pinecone** account (free tier available)
- **Stripe** account for payments
- **AWS S3** bucket (optional, for document storage)
- **Fresh API** key (optional, for LinkedIn scraping)

### Development Tools
- Git
- pip (Python package manager)
- virtualenv or venv
- Tesseract OCR (optional, for PDF OCR)

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/flock.git
cd flock
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Install Tesseract (Optional, for OCR)

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr
```

**Windows:**
Download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

### 5. Set Up PostgreSQL Database

```bash
# Create database
createdb flock_db

# Run schema migrations (create tables)
psql flock_db < schema.sql
```

### 6. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your credentials (see [Configuration](#configuration) section).

### 7. Initialize Pinecone Index

The application will automatically create the Pinecone index on first run, or you can manually initialize:

```python
from vector_store import VectorStore
vs = VectorStore()
# Index created automatically
```

---

## Configuration

Create a `.env` file in the project root with the following variables:

### Core Configuration
```bash
# Flask
SECRET_KEY=your-secret-key-here-change-in-production
FLASK_ENV=development  # or production

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/flock_db

# Redis
REDIS_URL=redis://localhost:6379/0
```

### AI Services
```bash
# OpenAI
OPENAI_API_KEY=sk-your-openai-api-key

# Pinecone
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_ENVIRONMENT=us-east-1  # or your region
```

### Payment Processing
```bash
# Stripe
STRIPE_SECRET_KEY=sk_test_your-stripe-secret-key
STRIPE_PRICE_ID=price_your-subscription-price-id
STRIPE_WEBHOOK_SECRET=whsec_your-webhook-secret
```

### External Services (Optional)
```bash
# AWS S3 (for document storage)
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_BUCKET_NAME=your-bucket-name
AWS_REGION=us-east-1

# Fresh API (for LinkedIn scraping)
FRESH_API_KEY=your-fresh-api-key

# Email (for notifications)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

### Security Settings
```bash
# Encryption
ENCRYPTION_KEY=your-32-byte-fernet-key

# CORS (if needed)
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

---

## Usage

### Starting the Application

#### Development Mode

1. **Start Redis** (if not running as service):
```bash
redis-server
```

2. **Start Celery Worker**:
```bash
celery -A tasks worker --loglevel=info
```

3. **Start Flask Application**:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

#### Production Mode

Use Gunicorn with multiple workers:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

### Common Tasks

#### Create an Organization
```bash
# Via web interface
1. Sign up / Log in
2. Complete onboarding profile
3. Navigate to "Create Organization"
4. Upload documents or add employees
```

#### Upload Documents
```bash
# Supported formats: PDF, DOCX, TXT, MD, CSV
POST /documents/upload
Content-Type: multipart/form-data

{
  "file": <file>,
  "org_id": 123,
  "category": "policies"  # optional
}
```

#### Query Knowledge Base
```bash
# RAG query endpoint
POST /chat
Content-Type: application/json

{
  "org_id": 123,
  "message": "What is our vacation policy?",
  "conversation_history": []  # optional
}
```

#### Run Matching Simulation
```bash
# Via web interface
1. Complete profile
2. Create organization
3. Add employees
4. Click "Run Matching Simulation"
```

---

## API Documentation

### Authentication Endpoints

#### POST `/signup`
Create new user account.
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123",
  "first_name": "John",
  "last_name": "Doe"
}
```

#### POST `/login`
Authenticate user.
```json
{
  "email": "user@example.com",
  "password": "SecurePassword123"
}
```

### Document Endpoints

#### POST `/documents/upload`
Upload document for processing.
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `file`: Document file
  - `org_id`: Organization ID
  - `category`: Optional category tag

#### GET `/documents/list?org_id=123`
List all documents for organization.

#### DELETE `/documents/<doc_id>`
Delete document and associated vectors.

### RAG Chat Endpoints

#### POST `/chat`
Query organizational knowledge base.
```json
{
  "org_id": 123,
  "message": "What are the company benefits?",
  "conversation_history": [
    {"role": "user", "content": "Previous question"},
    {"role": "assistant", "content": "Previous answer"}
  ]
}
```

**Response:**
```json
{
  "answer": "According to the Employee Handbook...",
  "sources": [
    {
      "filename": "handbook.pdf",
      "page": 5,
      "text": "...",
      "score": 0.89
    }
  ],
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 456,
    "total_tokens": 1690
  }
}
```

### Subscription Endpoints

#### POST `/subscription/create-checkout`
Create Stripe checkout session.

#### POST `/subscription/cancel`
Cancel active subscription.

#### GET `/subscription/status`
Get current subscription status.

### Admin Endpoints

#### GET `/admin/stats`
System-wide statistics (admin only).

#### POST `/admin/organizations/<org_id>/reprocess`
Reprocess all documents for organization.

---

## Deployment

### DigitalOcean App Platform

1. **Connect Repository**
   - Link GitHub repository to DigitalOcean

2. **Configure App Spec**
   Use the provided `FIXED_APP_SPEC.yaml`:
   ```yaml
   name: flock
   services:
     - name: web
       github:
         repo: yourusername/flock
         branch: main
       run_command: gunicorn --worker-class=gthread --threads=4 --workers=2 --bind=0.0.0.0:8080 wsgi:app
       environment_slug: python
   ```

3. **Set Environment Variables**
   Add all variables from `.env` in the DigitalOcean dashboard

4. **Add Database & Redis**
   - Add PostgreSQL managed database
   - Add Redis managed database
   - Copy connection strings to environment variables

5. **Deploy**
   ```bash
   doctl apps create --spec FIXED_APP_SPEC.yaml
   ```

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Install Tesseract for OCR
RUN apt-get update && apt-get install -y tesseract-ocr

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "wsgi:app"]
```

Build and run:
```bash
docker build -t flock .
docker run -p 5000:5000 --env-file .env flock
```

### Environment-Specific Configurations

#### Production Checklist
- [ ] Set `FLASK_ENV=production`
- [ ] Use strong `SECRET_KEY` (32+ random characters)
- [ ] Enable HTTPS/SSL
- [ ] Configure CORS for your domain
- [ ] Set up database backups
- [ ] Configure monitoring (e.g., Sentry)
- [ ] Set rate limits on API endpoints
- [ ] Review and harden security settings
- [ ] Set up log aggregation
- [ ] Configure CDN for static assets

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

### Quick Start for Contributors

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `pytest tests/`
5. Commit: `git commit -m 'Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Use type hints where applicable
- Write docstrings for all functions/classes
- Keep functions focused and under 50 lines
- Add tests for new features

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Support

### Documentation
- [API Reference](docs/api.md)
- [Architecture Guide](docs/architecture.md)
- [Deployment Guide](docs/deployment.md)

### Community
- **Issues**: [GitHub Issues](https://github.com/yourusername/flock/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/flock/discussions)
- **Email**: support@flockapp.com

### Getting Help
1. Check existing [Issues](https://github.com/yourusername/flock/issues)
2. Review [Documentation](docs/)
3. Ask in [Discussions](https://github.com/yourusername/flock/discussions)
4. Email support for private inquiries

---

## Acknowledgments

- OpenAI for GPT-4 and Whisper APIs
- Pinecone for vector database infrastructure
- Stripe for payment processing
- The Flask and Python communities

---

**Built with ❤️ by the Flock Team**
