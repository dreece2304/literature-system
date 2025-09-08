"""Database connection and session management."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator
import yaml

from src.models import Base

def load_config():
    """Load database configuration."""
    config_path = os.getenv('LITDB_CONFIG_PATH', 'config/settings.yml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config

def get_engine(config=None):
    """Create database engine."""
    if config is None:
        config = load_config()
    
    db_config = config['database']
    
    if db_config['type'] == 'sqlite':
        db_path = Path(db_config['path'])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_url = f"sqlite:///{db_path}"
    elif db_config['type'] == 'postgresql':
        db_url = f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}/{db_config['name']}"
    else:
        raise ValueError(f"Unsupported database type: {db_config['type']}")
    
    engine = create_engine(db_url, echo=False)
    return engine

def init_db():
    """Initialize database with tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized at {engine.url}")

def get_session() -> Generator[Session, None, None]:
    """Get database session."""
    engine = get_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
