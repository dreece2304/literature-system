"""Test configuration and shared fixtures."""
import os
import sys
import tempfile
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import application components
from src.models import Base
from src.database import get_session


@pytest.fixture(scope="session")
def test_database():
    """Create a temporary SQLite database for testing."""
    # Create temporary database file
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    # Create test database engine
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    yield engine, database_url
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def db_session(test_database):
    """Create a database session for testing."""
    engine, _ = test_database
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.rollback()
    session.close()


@pytest.fixture
def client(test_database):
    """Create a test client with test database."""
    engine, database_url = test_database
    
    # Override the database dependency
    def override_get_session():
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    # Import the app and override dependency
    from src.api.main import app, get_db
    app.dependency_overrides[get_db] = override_get_session
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Clean up
    app.dependency_overrides.clear()


@pytest.fixture
def sample_paper_data():
    """Sample paper data for testing."""
    return {
        "title": "Test Paper: Machine Learning in Materials Science",
        "abstract": "This paper explores the application of machine learning techniques to materials science research.",
        "year": 2024,
        "doi": "10.1000/test.doi.123",
        "arxiv_id": "2024.0001",
        "journal": "Journal of Test Science",
        "volume": "42",
        "issue": "1",
        "pages": "123-456",
        "publisher": "Test Publisher",
        "rating": 4,
        "read_status": "unread",
        "authors": ["Dr. Test Author", "Prof. Example Researcher"],
        "tags": ["machine learning", "materials science", "testing"],
        "collections": ["Test Collection"]
    }


@pytest.fixture
def sample_paper_update():
    """Sample paper update data for testing."""
    return {
        "rating": 5,
        "read_status": "read",
        "tags": ["machine learning", "materials science", "completed"],
        "abstract": "Updated abstract with more detailed information."
    }


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing event publishing."""
    class MockRedis:
        def __init__(self):
            self.published_events = []
            self.connected = True
        
        def publish(self, channel, message):
            """Mock publish method that records events."""
            import json
            self.published_events.append({
                'channel': channel,
                'message': message,
                'data': json.loads(message)
            })
            return 1  # Simulate successful publish
        
        def ping(self):
            """Mock ping method."""
            if not self.connected:
                raise Exception("Redis connection failed")
            return True
        
        @classmethod
        def from_url(cls, url, **kwargs):
            """Mock from_url class method."""
            return cls()
    
    return MockRedis()


@pytest.fixture
def mock_event_publisher(mock_redis, monkeypatch):
    """Mock event publisher that uses mock Redis."""
    from src.services.event_service import EventPublisher
    
    # Create event publisher with mocked Redis
    publisher = EventPublisher()
    monkeypatch.setattr(publisher, 'redis_client', mock_redis)
    monkeypatch.setattr(publisher, 'enabled', True)
    
    return publisher, mock_redis