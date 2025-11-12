# 📁 Project Structure

Complete guide to the Flock project organization and file structure.

---

## Overview

Flock follows a professional Python package structure with clear separation of concerns:

```
flock/
├── src/flock/          # Application source code (Python package)
├── tests/              # Test suite
├── docs/               # Documentation
├── config/             # Configuration files
├── scripts/            # Utility scripts
├── archives/           # Archived/deprecated code
├── wsgi.py            # WSGI entry point
├── setup.py           # Package installation
└── requirements.txt   # Dependencies
```

---

## Directory Structure

### 📱 `src/flock/` - Application Code

Main application package containing all Python modules.

```
src/flock/
├── __init__.py                 # Package initialization
├── app.py                      # Main Flask application (723KB)
├── logging_config.py           # Centralized logging configuration
│
├── Core Modules/
│   ├── data_safety.py          # Encryption & GDPR compliance
│   ├── payment.py              # Stripe payment integration
│   ├── email_followup.py       # Email notification system
│   ├── onboarding.py           # User onboarding & profiling
│   ├── onboarding_agent.py     # AI-powered onboarding
│   └── linkedin_scraper.py     # LinkedIn profile scraping
│
└── Knowledge Platform/
    ├── storage_manager.py      # Cloud storage (S3/DO Spaces)
    ├── document_processor.py   # PDF/DOCX extraction
    ├── text_chunker.py         # Smart text chunking
    ├── embedding_service.py    # OpenAI embeddings
    ├── vector_store.py         # Pinecone vector database
    ├── rag_pipeline.py         # RAG chat system
    ├── tasks.py                # Celery background tasks
    └── celery_config.py        # Celery configuration
```

**Key Files:**

| File | Lines | Purpose |
|------|-------|---------|
| **app.py** | 18,726 | Main Flask application with all routes |
| **onboarding.py** | 2,800+ | 10-step onboarding & profile creation |
| **tasks.py** | 800+ | Background document processing |
| **payment.py** | 500+ | Stripe subscription management |
| **storage_manager.py** | 250+ | S3/DO Spaces file management |

---

### 🧪 `tests/` - Test Suite

```
tests/
├── __init__.py
├── conftest.py                 # Pytest configuration
├── fixtures/                   # Test fixtures and data
├── unit/                       # Unit tests
│   ├── test_app.py
│   ├── test_payment.py
│   ├── test_data_safety.py
│   └── ...
├── integration/                # Integration tests
│   ├── test_api_endpoints.py
│   ├── test_payment_flow.py
│   └── ...
└── e2e/                        # End-to-end tests
    └── test_user_journey.py
```

**Status**: Tests to be added (Phase 2)

**Planned Coverage**:
- Unit tests: 80%+ coverage target
- Integration tests: All API endpoints
- E2E tests: Critical user journeys

---

### 📚 `docs/` - Documentation

```
docs/
├── CHANGELOG.md                # Version history
├── CODE_OF_CONDUCT.md          # Community standards
├── CONTRIBUTING.md             # Contribution guidelines
├── DEPLOYMENT.md               # Deployment guide
├── SECURITY.md                 # Security policy
├── OPEN_SOURCE_AUDIT_REPORT.md # Audit findings
├── PROJECT_STRUCTURE.md        # This file
│
└── (Future documentation)
    ├── API_REFERENCE.md        # Complete API docs
    ├── ARCHITECTURE.md         # System architecture
    └── DEVELOPMENT.md          # Development guide
```

---

### ⚙️ `config/` - Configuration Files

```
config/
├── FIXED_APP_SPEC.yaml         # DigitalOcean App Platform spec
├── .python-version             # Python version (3.11)
└── (Future configs)
    ├── nginx.conf              # Nginx configuration
    ├── supervisor.conf         # Process management
    └── docker-compose.yml      # Docker composition
```

---

### 🔧 `scripts/` - Utility Scripts

```
scripts/
└── (To be added)
    ├── setup_dev.sh            # Development environment setup
    ├── backup_db.sh            # Database backup script
    ├── deploy.sh               # Deployment automation
    └── migrate_db.py           # Database migrations
```

---

### 🗄️ `archives/` - Archived Code

```
archives/
├── deprecated_code/
│   ├── enhanced_matching_system.py  # Old ML matching (96KB)
│   ├── chat_agents.py               # Unused chat agents
│   └── document_classifier.py       # Unused classifier
│
├── backups/
│   ├── app.py.backup                # Previous app version
│   └── app.py.backup_voice_buttons  # Voice feature backup
│
├── old_docs/
│   └── *.md                         # Historical documentation
│
└── old_tests/
    ├── tests/                       # Old test files
    └── test_end_to_end.py          # Legacy E2E test
```

---

## Root Level Files

### Entry Points

**wsgi.py** - WSGI entry point for production servers
```python
# Usage with gunicorn:
gunicorn wsgi:app --bind 0.0.0.0:8080 --workers 4
```

**setup.py** - Package installation and distribution
```bash
# Development installation (editable):
pip install -e .

# Production installation:
pip install .
```

### Configuration

**requirements.txt** - Python dependencies
- 25+ packages organized by category
- System dependencies documented
- Version pinning for stability

**.env.example** - Environment variable template
- 40+ configuration variables
- Security generation commands
- Required vs. optional designation

**.gitignore** - Git exclusions
- 200+ patterns
- Security-focused (credentials, keys, etc.)
- Build artifacts, caches, logs

**Procfile** - Process definitions for deployment
```
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT
worker: celery -A flock.celery_config.celery_app worker
```

**Aptfile** - System dependencies
```
poppler-utils      # PDF processing
tesseract-ocr      # OCR capabilities
libmagic1          # File type detection
```

### Documentation

**README.md** - Project overview and getting started
**LICENSE** - MIT License
**COMPLETION_SUMMARY.md** - Full audit completion report

---

## Import Structure

### Package Imports

With the new structure, imports follow this pattern:

```python
# From root (wsgi.py, scripts)
from flock import app
from flock.app import init_database
from flock.celery_config import celery_app

# Within the package (module to module)
from flock.data_safety import DataEncryption
from flock.payment import SubscriptionManager
from flock.logging_config import get_logger

# External imports
from flask import Flask, request, session
from openai import OpenAI
```

### Path Configuration

The `wsgi.py` file adds `src/` to the Python path:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
```

This allows the package to be imported as `flock` from anywhere.

---

## Development Workflow

### Setting Up

```bash
# 1. Clone repository
git clone https://github.com/your-username/flock.git
cd flock

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 3. Install in development mode
pip install -e .

# 4. Install development dependencies
pip install -e ".[dev]"

# 5. Configure environment
cp .env.example .env
# Edit .env with your values
```

### Running the Application

```bash
# Development server (with auto-reload)
python wsgi.py

# Production server
gunicorn wsgi:app --bind 0.0.0.0:8080 --workers 4

# With Celery worker
celery -A flock.celery_config.celery_app worker --loglevel=info
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=flock --cov-report=html

# Specific test file
pytest tests/unit/test_app.py

# With verbose output
pytest -v
```

### Code Quality

```bash
# Format code
black src/flock/

# Sort imports
isort src/flock/

# Lint code
flake8 src/flock/

# Type checking
mypy src/flock/
```

---

## File Size Summary

| Category | Files | Size | Percentage |
|----------|-------|------|------------|
| **Application Code** | 17 | 1.0 MB | 62% |
| **Documentation** | 10 | 117 KB | 7% |
| **Configuration** | 7 | 12 KB | 1% |
| **Archives** | 23 | 1.8 MB | 30% |
| **Total** | 57 | 2.9 MB | 100% |

---

## Adding New Features

### 1. Create New Module

```bash
# Create module file
touch src/flock/new_feature.py
```

```python
# src/flock/new_feature.py
"""
Module description
"""

from flock.logging_config import get_logger

logger = get_logger(__name__)

class NewFeature:
    """Feature class"""
    pass
```

### 2. Write Tests

```bash
# Create test file
touch tests/unit/test_new_feature.py
```

```python
# tests/unit/test_new_feature.py
import pytest
from flock.new_feature import NewFeature

def test_new_feature():
    feature = NewFeature()
    assert feature is not None
```

### 3. Update Documentation

- Add to `docs/API_REFERENCE.md`
- Update `CHANGELOG.md`
- Add usage example to `README.md`

### 4. Create Pull Request

Follow guidelines in `docs/CONTRIBUTING.md`

---

## Migration from Old Structure

### What Changed

**Before (Flat Structure):**
```
flock/
├── app.py
├── payment.py
├── data_safety.py
└── ... (all files in root)
```

**After (Package Structure):**
```
flock/
├── src/flock/
│   ├── __init__.py
│   ├── app.py
│   ├── payment.py
│   └── ...
├── docs/
├── tests/
└── wsgi.py
```

### Import Updates

**Old imports:**
```python
from app import init_database
from payment import SubscriptionManager
```

**New imports:**
```python
from flock.app import init_database
from flock.payment import SubscriptionManager
```

### No Impact On

- ✅ Deployment configurations (Procfile, FIXED_APP_SPEC.yaml)
- ✅ Environment variables (.env)
- ✅ External API endpoints
- ✅ Database schema
- ✅ Celery tasks

---

## Best Practices

### Code Organization

1. **One module, one purpose** - Each file should have a single, clear responsibility
2. **Logical grouping** - Related functionality stays together
3. **Minimal coupling** - Modules should be as independent as possible
4. **Clear naming** - File and function names should be descriptive

### Import Guidelines

1. **Absolute imports** - Always use `from flock.module import thing`
2. **No circular imports** - Structure code to avoid circular dependencies
3. **Group imports** - Standard library, third-party, local (separated by blank lines)
4. **Sort imports** - Use `isort` to maintain consistent ordering

### Documentation

1. **Docstrings** - Every public function and class should have a docstring
2. **Type hints** - Add type annotations to all function signatures
3. **Comments** - Explain complex logic, not obvious code
4. **README files** - Add README.md in directories with complex structure

---

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'flock'`

**Solution**:
```bash
# Ensure src/ is in Python path
export PYTHONPATH="${PYTHONPATH}:./src"

# Or install package
pip install -e .
```

### File Not Found

**Problem**: Configuration files not found

**Solution**: Check working directory
```bash
# Run from project root
cd /path/to/flock
python wsgi.py
```

### Module Import Order

**Problem**: Circular import errors

**Solution**: Review import order, consider lazy imports
```python
# Instead of:
from flock.app import some_function

# Use lazy import:
def my_function():
    from flock.app import some_function
    return some_function()
```

---

## Future Improvements

### Planned Additions

1. **Database Migrations** (`scripts/migrations/`)
   - Alembic integration
   - Version control for schema changes

2. **API Documentation** (`docs/api/`)
   - OpenAPI/Swagger specification
   - Interactive API explorer

3. **Docker Support** (`docker/`)
   - Dockerfile
   - docker-compose.yml
   - Multi-stage builds

4. **CI/CD Pipelines** (`.github/workflows/`)
   - Automated testing
   - Code quality checks
   - Automated deployments

5. **Monitoring** (`scripts/monitoring/`)
   - Health check scripts
   - Performance monitoring
   - Alert configuration

---

## Resources

- **Python Package Guide**: https://packaging.python.org/
- **Flask Project Structure**: https://flask.palletsprojects.com/patterns/packages/
- **Celery Best Practices**: https://docs.celeryq.dev/en/stable/userguide/tasks.html
- **Testing with Pytest**: https://docs.pytest.org/

---

**Last Updated**: November 12, 2024
**Version**: 1.0.0
