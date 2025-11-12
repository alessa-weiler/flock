# Contributing to Flock

First off, thank you for considering contributing to Flock! It's people like you that make Flock such a great tool for AI-powered professional networking and knowledge management.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Your First Code Contribution](#your-first-code-contribution)
  - [Pull Requests](#pull-requests)
- [Development Setup](#development-setup)
- [Code Style Guidelines](#code-style-guidelines)
- [Testing Requirements](#testing-requirements)
- [Commit Message Conventions](#commit-message-conventions)
- [Pull Request Process](#pull-request-process)
- [Security Vulnerability Reporting](#security-vulnerability-reporting)
- [Community and Communication](#community-and-communication)

---

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@flockapp.com.

### Our Standards

**Examples of behavior that contributes to a positive environment:**
- Using welcoming and inclusive language
- Being respectful of differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

**Examples of unacceptable behavior:**
- Trolling, insulting/derogatory comments, and personal or political attacks
- Public or private harassment
- Publishing others' private information without explicit permission
- Other conduct which could reasonably be considered inappropriate in a professional setting

---

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the [existing issues](https://github.com/yourusername/flock/issues) as you might find that you don't need to create one. When you are creating a bug report, please include as many details as possible.

#### How to Submit a Good Bug Report

Bugs are tracked as [GitHub issues](https://github.com/yourusername/flock/issues). Create an issue and provide the following information:

- **Use a clear and descriptive title** for the issue
- **Describe the exact steps which reproduce the problem** in as many details as possible
- **Provide specific examples** to demonstrate the steps
- **Describe the behavior you observed** after following the steps
- **Explain which behavior you expected to see instead** and why
- **Include screenshots or animated GIFs** if relevant
- **Include error logs** if applicable

**Template:**
```markdown
**Bug Description**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '...'
3. Scroll down to '...'
4. See error

**Expected Behavior**
A clear and concise description of what you expected to happen.

**Screenshots**
If applicable, add screenshots to help explain your problem.

**Environment:**
 - OS: [e.g. macOS 14.0]
 - Python Version: [e.g. 3.9.7]
 - Flask Version: [e.g. 2.3.3]
 - Browser: [e.g. Chrome 118]

**Additional Context**
Add any other context about the problem here.

**Logs**
```
Paste relevant log output here
```
```

### Suggesting Enhancements

Enhancement suggestions are tracked as [GitHub issues](https://github.com/yourusername/flock/issues). Create an issue and provide the following information:

- **Use a clear and descriptive title**
- **Provide a detailed description** of the suggested enhancement
- **Explain why this enhancement would be useful** to most Flock users
- **List some examples** of how it would be used
- **Specify which version** of Flock you're using

**Template:**
```markdown
**Feature Request**
A clear and concise description of what you want to happen.

**Use Case**
Describe the problem you're trying to solve or the workflow you want to improve.

**Proposed Solution**
Describe how you envision this feature working.

**Alternatives Considered**
Describe any alternative solutions or features you've considered.

**Additional Context**
Add any other context or screenshots about the feature request here.
```

### Your First Code Contribution

Unsure where to begin? You can start by looking through these issues:

- `good-first-issue` - Issues which should only require a few lines of code
- `help-wanted` - Issues which need attention but are slightly more involved

#### Setting Up Your Development Environment

See the [Development Setup](#development-setup) section below for detailed instructions.

### Pull Requests

- Fill in the required template
- Follow the [Code Style Guidelines](#code-style-guidelines)
- Include tests for new features
- Update documentation as needed
- Ensure all tests pass locally before submitting

---

## Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR-USERNAME/flock.git
cd flock
git remote add upstream https://github.com/ORIGINAL-OWNER/flock.git
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov black flake8 mypy pre-commit
```

### 4. Install Pre-commit Hooks

```bash
pre-commit install
```

This will automatically run linting and formatting checks before each commit.

### 5. Set Up Environment Variables

```bash
cp .env.example .env
# Edit .env with your development credentials
```

### 6. Set Up Database

```bash
# Create development database
createdb flock_dev

# Run migrations
psql flock_dev < schema.sql
```

### 7. Start Development Services

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery Worker
celery -A tasks worker --loglevel=info

# Terminal 3: Flask App
python app.py
```

### 8. Verify Installation

```bash
# Run tests
pytest tests/

# Check code style
black --check .
flake8 .
mypy .
```

---

## Code Style Guidelines

### Python Style (PEP 8)

We follow [PEP 8](https://peps.python.org/pep-0008/) with some modifications:

- **Line Length**: Maximum 100 characters (not 79)
- **Formatting**: Use [Black](https://black.readthedocs.io/) with default settings
- **Import Order**: Use [isort](https://pycqa.github.io/isort/) to organize imports

### Code Formatting

**Automatically format code before committing:**
```bash
black .
isort .
```

### Type Hints

Use type hints for all function signatures:

```python
from typing import List, Dict, Optional

def process_document(
    doc_path: str,
    org_id: int,
    categories: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Process a document and extract metadata.

    Args:
        doc_path: Path to the document file
        org_id: Organization ID
        categories: Optional list of category tags

    Returns:
        Dictionary containing extracted text and metadata

    Raises:
        ValueError: If document format is unsupported
    """
    pass
```

### Docstrings

Use Google-style docstrings for all public functions, classes, and methods:

```python
def search_vectors(
    query: str,
    top_k: int = 10,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    Search for similar vectors in the knowledge base.

    This function generates an embedding for the query and searches
    the Pinecone vector database for semantically similar documents.

    Args:
        query: User's search query
        top_k: Number of results to return
        filters: Optional metadata filters to apply

    Returns:
        List of dictionaries containing:
            - id: Vector ID
            - score: Similarity score (0-1)
            - metadata: Document metadata

    Example:
        >>> results = search_vectors("vacation policy", top_k=5)
        >>> print(results[0]['metadata']['filename'])
        'employee_handbook.pdf'

    Note:
        Results are automatically filtered by organization namespace.
    """
    pass
```

### Naming Conventions

- **Functions and Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private Methods**: `_leading_underscore`

```python
# Good
class DocumentProcessor:
    MAX_FILE_SIZE = 10_000_000

    def __init__(self):
        self._cache = {}

    def process_file(self, file_path: str) -> Dict:
        pass

    def _extract_metadata(self, doc: Any) -> Dict:
        pass

# Bad
class documentProcessor:
    maxFileSize = 10000000

    def ProcessFile(self, FilePath):
        pass
```

### Error Handling

Always provide meaningful error messages:

```python
# Good
try:
    embedding = generate_embedding(text, org_id)
except RateLimitError as e:
    logger.error(f"OpenAI rate limit exceeded for org {org_id}: {e}")
    raise APIError(
        "Embedding service temporarily unavailable. Please try again in a moment."
    ) from e

# Bad
try:
    embedding = generate_embedding(text, org_id)
except Exception as e:
    print("Error")
    raise
```

### Logging

Use the `logging` module, not `print()` statements:

```python
import logging

logger = logging.getLogger(__name__)

# Good
logger.info(f"Processing document {doc_id} for organization {org_id}")
logger.warning(f"Document {doc_id} has no extractable text")
logger.error(f"Failed to upload to S3: {error}", exc_info=True)

# Bad
print(f"Processing document {doc_id}")
```

### Function Length

Keep functions focused and under 50 lines. If a function is longer, consider breaking it into smaller functions:

```python
# Good
def process_document(file_path: str, org_id: int) -> Dict:
    """Process document and store in vector database."""
    text = _extract_text(file_path)
    chunks = _chunk_text(text)
    embeddings = _generate_embeddings(chunks, org_id)
    _store_vectors(embeddings, org_id)
    return {'status': 'success', 'chunks': len(chunks)}

# Bad - one giant function with 200+ lines
```

---

## Testing Requirements

### Test Coverage

All new features must include tests. Aim for:
- **Minimum 80% code coverage** for new code
- **100% coverage** for critical paths (authentication, payment processing)

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_rag_pipeline.py

# Run specific test
pytest tests/test_rag_pipeline.py::test_retrieve_documents
```

### Writing Tests

Use `pytest` with fixtures for test setup:

```python
import pytest
from vector_store import VectorStore

@pytest.fixture
def vector_store():
    """Create a test vector store instance."""
    vs = VectorStore(index_name="test-index")
    yield vs
    # Cleanup after tests
    vs.delete_namespace(org_id=999)

def test_upsert_document_chunks(vector_store):
    """Test upserting document chunks to Pinecone."""
    org_id = 999
    doc_id = 1
    chunks = [
        {'index': 0, 'text': 'Test chunk', 'tokens': 10},
    ]
    embeddings = [[0.1] * 3072]  # Mock embedding

    result = vector_store.upsert_document_chunks(
        org_id=org_id,
        doc_id=doc_id,
        chunks=chunks,
        embeddings=embeddings
    )

    assert result['upserted_count'] == 1
    assert result['doc_id'] == doc_id

def test_search_returns_relevant_results(vector_store):
    """Test vector search returns relevant results."""
    # Setup test data
    # ... setup code ...

    # Execute search
    results = vector_store.search(
        org_id=999,
        query_embedding=[0.1] * 3072,
        top_k=5
    )

    # Assertions
    assert len(results) > 0
    assert results[0]['score'] > 0.7
    assert 'metadata' in results[0]
```

### Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_auth.py             # Authentication tests
├── test_document_processor.py
├── test_embedding_service.py
├── test_vector_store.py
├── test_rag_pipeline.py
├── test_payment.py
└── integration/
    ├── test_end_to_end.py   # Full workflow tests
    └── test_api_endpoints.py
```

---

## Commit Message Conventions

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring without changing functionality
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates

### Examples

```bash
# Feature
feat(rag): add streaming support for RAG queries

Implements server-sent events for streaming GPT-4 responses
to improve user experience for long-form answers.

Closes #123

# Bug fix
fix(auth): resolve session timeout issue

Sessions were expiring prematurely due to incorrect
cookie settings. Updated to use permanent sessions
with 24-hour timeout.

Fixes #456

# Documentation
docs(readme): update installation instructions

Added section on Tesseract OCR installation for
different operating systems.

# Refactoring
refactor(vector-store): simplify metadata sanitization

Extracted metadata cleaning logic into separate method
for better testability and reusability.

# Performance
perf(embeddings): implement batch processing for large documents

Reduced embedding generation time by 60% through
parallel batch processing.
```

### Rules

1. Use present tense ("add feature" not "added feature")
2. Use imperative mood ("move cursor to..." not "moves cursor to...")
3. Don't capitalize first letter
4. No period (.) at the end of the subject line
5. Limit subject line to 50 characters
6. Separate subject from body with a blank line
7. Wrap body at 72 characters
8. Use body to explain what and why, not how

---

## Pull Request Process

### Before Submitting

1. **Update your branch** with the latest upstream changes:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all tests** and ensure they pass:
   ```bash
   pytest
   ```

3. **Check code style**:
   ```bash
   black --check .
   flake8 .
   mypy .
   ```

4. **Update documentation** if needed

5. **Add tests** for new features

### Creating the Pull Request

1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Go to the [Flock repository](https://github.com/yourusername/flock) and create a Pull Request

3. Fill out the PR template completely:

```markdown
## Description
Brief description of what this PR does and why.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Related Issues
Closes #123
Related to #456

## Testing
- [ ] All tests pass locally
- [ ] Added new tests for this feature
- [ ] Updated existing tests
- [ ] Manual testing completed

## Checklist
- [ ] Code follows the style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings generated
- [ ] Tests added/updated
- [ ] All tests passing

## Screenshots (if applicable)
Add screenshots to help explain your changes.

## Additional Notes
Any additional information reviewers should know.
```

### Review Process

1. **Automated checks** will run (tests, linting, coverage)
2. **Maintainer review** - at least one approval required
3. **Address feedback** - make requested changes
4. **Final approval** - maintainer will merge

### After Merging

1. Delete your branch:
   ```bash
   git branch -d feature/your-feature-name
   git push origin --delete feature/your-feature-name
   ```

2. Update your local main:
   ```bash
   git checkout main
   git pull upstream main
   ```

---

## Security Vulnerability Reporting

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: **security@flockapp.com**

Include the following information:
- Type of vulnerability
- Full paths of source file(s) related to the vulnerability
- Location of the affected source code (tag/branch/commit)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue

We will respond within 48 hours and work with you to understand and resolve the issue.

### Responsible Disclosure

We practice responsible disclosure:
1. You report the vulnerability privately
2. We confirm and fix the issue
3. We publicly disclose the vulnerability after a fix is released
4. We credit you in the security advisory (if you wish)

---

## Community and Communication

### Where to Get Help

- **Documentation**: Check the [README](README.md) and docs folder first
- **GitHub Discussions**: For questions and general discussion
- **GitHub Issues**: For bug reports and feature requests
- **Email**: support@flockapp.com for private inquiries

### Staying Updated

- **Watch the repository** for notifications
- **Star the project** to show support
- **Follow the project** on social media

### Recognition

Contributors are recognized in several ways:
- Listed in [CONTRIBUTORS.md](CONTRIBUTORS.md)
- Mentioned in release notes for significant contributions
- Special badges for different contribution types
- Invited to join the core contributor team for sustained contributions

---

## Additional Resources

### Learning Materials

- [Flask Documentation](https://flask.palletsprojects.com/)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Pinecone Documentation](https://docs.pinecone.io/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Celery Documentation](https://docs.celeryproject.org/)

### Tools

- [Black Code Formatter](https://black.readthedocs.io/)
- [pytest Testing Framework](https://docs.pytest.org/)
- [mypy Type Checker](https://mypy.readthedocs.io/)
- [Pre-commit Hooks](https://pre-commit.com/)

### Project Resources

- [Architecture Documentation](docs/architecture.md)
- [API Reference](docs/api.md)
- [Deployment Guide](docs/deployment.md)

---

## Questions?

If you have any questions about contributing, please:
1. Check the [FAQ](docs/faq.md)
2. Search [existing issues and discussions](https://github.com/yourusername/flock/issues)
3. Ask in [GitHub Discussions](https://github.com/yourusername/flock/discussions)
4. Contact us at contribute@flockapp.com

---

Thank you for contributing to Flock! 🎉

Every contribution, no matter how small, makes a difference. We appreciate your time and effort in making Flock better for everyone.
