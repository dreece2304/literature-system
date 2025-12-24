"""API routers for literature database service."""
from .citations import router as citations_router
from .integration import router as integration_router

__all__ = ['citations_router', 'integration_router']
