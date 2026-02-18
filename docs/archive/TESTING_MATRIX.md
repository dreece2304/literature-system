# Testing Requirements Matrix

## Testing Levels Overview

| Level | Purpose | When to Run | Coverage Target |
|-------|---------|-------------|-----------------|
| **Unit Tests** | Test individual functions | Every commit | >80% |
| **Integration Tests** | Test service interactions | Before merge | >70% |
| **E2E Tests** | Test complete workflows | Before release | Critical paths |
| **Performance Tests** | Test speed and load | Weekly | Benchmarks |
| **Security Tests** | Test vulnerabilities | Monthly | All endpoints |

## Service Testing Requirements

### Literature Database Service

| Component | Unit Tests | Integration | E2E | Notes |
|-----------|------------|-------------|-----|--------|
| **Models** | ✅ Required | ✅ Required | - | Test all CRUD operations |
| **API Endpoints** | ✅ Required | ✅ Required | ✅ Required | Test all HTTP methods |
| **PDF Extraction** | ✅ Required | ⚡ Optional | - | Mock file operations |
| **Text Processing** | ✅ Required | - | - | Test edge cases |
| **Zotero Sync** | ✅ Required | ✅ Required | - | Mock Zotero API |
| **Search Index** | ✅ Required | ✅ Required | - | Test indexing and queries |
| **File Storage** | ✅ Required | ⚡ Optional | - | Use temp directories |
| **Database Ops** | ✅ Required | ✅ Required | - | Use test database |

### Literature AI Service

| Component | Unit Tests | Integration | E2E | Notes |
|-----------|------------|-------------|-----|--------|
| **LLM Agents** | ✅ Required | ✅ Required | ⚡ Optional | Mock LLM responses |
| **Embeddings** | ✅ Required | ✅ Required | - | Test vector operations |
| **Triage Logic** | ✅ Required | ✅ Required | ✅ Required | Test scoring accuracy |
| **Writing Assistant** | ✅ Required | ✅ Required | ✅ Required | Test suggestions |
| **Context Detection** | ✅ Required | - | - | Test parsing logic |
| **Memory Management** | ✅ Required | ⚡ Optional | - | Test OOM handling |
| **Vector DB** | ✅ Required | ✅ Required | - | Use test collection |
| **Streaming** | ⚡ Optional | ✅ Required | - | Test WebSocket |

### Literature Search Service

| Component | Unit Tests | Integration | E2E | Notes |
|-----------|------------|-------------|-----|--------|
| **API Clients** | ✅ Required | ⚡ Optional | - | Mock external APIs |
| **Rate Limiting** | ✅ Required | ✅ Required | - | Test throttling |
| **Result Parsing** | ✅ Required | - | - | Test all formats |
| **Deduplication** | ✅ Required | - | - | Test matching logic |
| **Error Handling** | ✅ Required | ✅ Required | - | Test all error codes |
| **Caching** | ✅ Required | ⚡ Optional | - | Test cache hits/misses |
| **PDF Fetching** | ⚡ Optional | ⚡ Optional | - | Mock downloads |

### API Gateway

| Component | Unit Tests | Integration | E2E | Notes |
|-----------|------------|-------------|-----|--------|
| **Routing** | ✅ Required | ✅ Required | ✅ Required | Test all routes |
| **Auth Middleware** | ✅ Required | ✅ Required | ✅ Required | Test auth flows |
| **Rate Limiting** | ✅ Required | ✅ Required | - | Test limits |
| **Error Handling** | ✅ Required | ✅ Required | - | Test error propagation |
| **Health Checks** | ✅ Required | ✅ Required | - | Test all services |
| **Request Validation** | ✅ Required | - | - | Test validators |
| **Response Formatting** | ✅ Required | - | - | Test transformers |

### Web Dashboard

| Component | Unit Tests | Integration | E2E | Notes |
|-----------|------------|-------------|-----|--------|
| **React Components** | ⚡ Optional | ✅ Required | ✅ Required | Test with React Testing Library |
| **State Management** | ✅ Required | - | - | Test Redux/Context |
| **API Calls** | ✅ Required | ✅ Required | - | Mock API responses |
| **File Upload** | ⚡ Optional | ✅ Required | ✅ Required | Test drag-and-drop |
| **Search UI** | ⚡ Optional | ✅ Required | ✅ Required | Test filters |
| **Writing Assistant UI** | ⚡ Optional | ✅ Required | ✅ Required | Test suggestions |
| **Visualizations** | ⚡ Optional | ⚡ Optional | - | Test graph rendering |

## Test File Structure

```
research/
├── infrastructure/
│   ├── literature-database/
│   │   └── tests/
│   │       ├── unit/
│   │       │   ├── test_models.py
│   │       │   ├── test_extractors.py
│   │       │   └── test_utils.py
│   │       ├── integration/
│   │       │   ├── test_api.py
│   │       │   └── test_database.py
│   │       └── conftest.py
│   ├── literature-ai/
│   │   └── tests/
│   │       ├── unit/
│   │       │   ├── test_agents.py
│   │       │   └── test_embeddings.py
│   │       ├── integration/
│   │       │   └── test_llm_integration.py
│   │       └── fixtures/
│   │           └── mock_responses.json
│   └── [other services...]
└── tests/
    ├── e2e/
    │   ├── test_paper_workflow.py
    │   ├── test_writing_workflow.py
    │   └── test_search_workflow.py
    ├── performance/
    │   ├── test_load.py
    │   └── test_benchmarks.py
    └── security/
        └── test_vulnerabilities.py
```

## Test Implementation Examples

### Unit Test Example
```python
# infrastructure/literature-database/tests/unit/test_models.py
import pytest
from src.models import Paper, Author

class TestPaperModel:
    def test_create_paper(self):
        """Test paper creation with required fields."""
        paper = Paper(
            title="Test Paper",
            authors=[Author(name="Test Author")]
        )
        assert paper.title == "Test Paper"
        assert len(paper.authors) == 1
        assert paper.status == "unread"
    
    def test_paper_validation(self):
        """Test paper validation rules."""
        with pytest.raises(ValueError):
            Paper(title="")  # Empty title should fail
    
    def test_paper_doi_format(self):
        """Test DOI format validation."""
        paper = Paper(
            title="Test",
            doi="10.1234/test"
        )
        assert paper.doi.startswith("10.")
```

### Integration Test Example
```python
# infrastructure/literature-database/tests/integration/test_api.py
import pytest
from fastapi.testclient import TestClient
from src.api import app

class TestPaperAPI:
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_create_and_retrieve_paper(self, client, test_db):
        """Test full paper lifecycle through API."""
        # Create paper
        response = client.post(
            "/api/v1/papers",
            json={"title": "Test Paper", "year": 2024}
        )
        assert response.status_code == 201
        paper_id = response.json()["id"]
        
        # Retrieve paper
        response = client.get(f"/api/v1/papers/{paper_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Test Paper"
        
        # Update paper
        response = client.put(
            f"/api/v1/papers/{paper_id}",
            json={"status": "read"}
        )
        assert response.status_code == 200
        
        # Delete paper
        response = client.delete(f"/api/v1/papers/{paper_id}")
        assert response.status_code == 204
```

### E2E Test Example
```python
# tests/e2e/test_paper_workflow.py
import pytest
from playwright.sync_api import Page

class TestPaperWorkflow:
    def test_complete_paper_import_workflow(self, page: Page, services_running):
        """Test importing a paper from upload to reading."""
        # Navigate to dashboard
        page.goto("http://localhost:3000")
        
        # Upload PDF
        page.set_input_files("#file-upload", "tests/fixtures/sample.pdf")
        page.click("#upload-button")
        
        # Wait for processing
        page.wait_for_selector(".paper-card", timeout=10000)
        
        # Verify paper appears
        assert page.locator(".paper-title").text_content() == "Sample Paper"
        
        # Mark as read
        page.click(".mark-read-button")
        
        # Verify status updated
        assert page.locator(".paper-status").text_content() == "read"
```

## Testing Commands

### Run All Tests
```bash
# Run all tests for a service
cd infrastructure/literature-database
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test level
pytest tests/unit/
pytest tests/integration/
```

### Pre-Commit Testing Checklist
```bash
#!/bin/bash
# scripts/pre_commit_tests.sh

echo "Running pre-commit tests..."

# 1. Format check
echo "Checking code format..."
black --check src/ tests/

# 2. Lint check
echo "Running linter..."
pylint src/

# 3. Type check
echo "Checking types..."
mypy src/

# 4. Unit tests
echo "Running unit tests..."
pytest tests/unit/ -q

# 5. Check for secrets
echo "Checking for secrets..."
grep -r "api_key\|password\|secret" src/ --exclude-dir=__pycache__

# 6. Verify no absolute paths
echo "Checking for absolute paths..."
grep -r "/home/\|C:\\" src/ --exclude-dir=__pycache__

echo "✅ All checks passed!"
```

## Coverage Requirements

### Minimum Coverage by Service

| Service | Unit Coverage | Integration Coverage | Overall |
|---------|---------------|---------------------|---------|
| Literature Database | 85% | 70% | 80% |
| Literature AI | 80% | 60% | 75% |
| Literature Search | 80% | 60% | 75% |
| API Gateway | 90% | 80% | 85% |
| Web Dashboard | 60% | 50% | 55% |

### Coverage Report Commands
```bash
# Generate HTML coverage report
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Generate terminal report
pytest --cov=src --cov-report=term-missing

# Fail if below threshold
pytest --cov=src --cov-fail-under=80
```

## Mock Strategies

### External Services
```python
# Mock external APIs
@pytest.fixture
def mock_arxiv(monkeypatch):
    def mock_search(*args, **kwargs):
        return [{"title": "Test Paper", "doi": "10.1234/test"}]
    monkeypatch.setattr("src.clients.arxiv.search", mock_search)

# Mock LLM responses
@pytest.fixture
def mock_llm(monkeypatch):
    def mock_generate(*args, **kwargs):
        return {"response": "Mocked LLM response"}
    monkeypatch.setattr("ollama.generate", mock_generate)

# Mock file operations
@pytest.fixture
def temp_pdf(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"Mock PDF content")
    return pdf_path
```

## CI/CD Integration

### GitHub Actions Workflow
```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        pytest --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

## Performance Testing

### Load Testing with Locust
```python
# tests/performance/locustfile.py
from locust import HttpUser, task, between

class LiteratureUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def search_papers(self):
        self.client.get("/api/v1/papers?search=machine+learning")
    
    @task(1)
    def get_paper(self):
        self.client.get("/api/v1/papers/1")
    
    @task(2)
    def create_paper(self):
        self.client.post("/api/v1/papers", json={
            "title": f"Test Paper",
            "authors": [{"name": "Test Author"}]
        })
```

### Run Load Tests
```bash
# Install locust
pip install locust

# Run load test
locust -f tests/performance/locustfile.py --host=http://localhost:8000

# Run headless
locust -f tests/performance/locustfile.py \
  --host=http://localhost:8000 \
  --users 100 \
  --spawn-rate 10 \
  --time 60s \
  --headless
```

## Security Testing

### Basic Security Checks
```python
# tests/security/test_vulnerabilities.py
import pytest
from fastapi.testclient import TestClient

class TestSecurity:
    def test_sql_injection(self, client):
        """Test SQL injection prevention."""
        response = client.get("/api/v1/papers?search=' OR '1'='1")
        assert response.status_code in [200, 400]
        # Should not return all papers
    
    def test_xss_prevention(self, client):
        """Test XSS prevention."""
        payload = "<script>alert('XSS')</script>"
        response = client.post("/api/v1/papers", json={
            "title": payload
        })
        if response.status_code == 201:
            # Check the script tags are escaped
            assert "<script>" not in response.text
    
    def test_path_traversal(self, client):
        """Test path traversal prevention."""
        response = client.get("/api/v1/files/../../../etc/passwd")
        assert response.status_code in [400, 404]
    
    def test_rate_limiting(self, client):
        """Test rate limiting."""
        for i in range(100):
            response = client.get("/api/v1/papers")
        
        # Should eventually get rate limited
        response = client.get("/api/v1/papers")
        assert response.status_code == 429
```

## Test Data Management

### Fixtures Directory Structure
```
tests/fixtures/
├── pdfs/
│   ├── valid.pdf
│   ├── corrupted.pdf
│   └── large.pdf
├── data/
│   ├── papers.json
│   ├── authors.json
│   └── zotero_export.rdf
└── responses/
    ├── arxiv_response.json
    ├── llm_response.json
    └── error_response.json
```

### Database Fixtures
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from src.models import Base

@pytest.fixture(scope="session")
def test_db():
    """Create test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def sample_papers(test_db):
    """Load sample papers."""
    papers = [
        Paper(title="Paper 1", year=2023),
        Paper(title="Paper 2", year=2024),
    ]
    session = Session(test_db)
    session.add_all(papers)
    session.commit()
    return papers
```