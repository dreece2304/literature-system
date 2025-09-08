"""Event publishing service for literature-database service."""
import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not installed. Event publishing will be disabled.")

# Import shared event types
import sys
from pathlib import Path
shared_path = str(Path(__file__).parent.parent.parent.parent.parent / "shared")
sys.path.insert(0, shared_path)

import importlib.util
spec = importlib.util.spec_from_file_location(
    "api_contracts", 
    Path(shared_path) / "types" / "api_contracts.py"
)
api_contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_contracts)

PaperEvent = api_contracts.PaperEvent
SyncEvent = api_contracts.SyncEvent


class EventPublisher:
    """Service for publishing events to Redis channels."""
    
    def __init__(self, redis_url: Optional[str] = None, service_name: str = "literature-database"):
        """
        Initialize event publisher.
        
        Args:
            redis_url: Redis connection URL. Defaults to environment variable REDIS_URL
            service_name: Name of the service publishing events
        """
        self.service_name = service_name
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = None
        self.enabled = REDIS_AVAILABLE
        
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available. Events will be logged but not published.")
            return
        
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
            self.enabled = True
        except Exception as e:
            logger.warning(f"Failed to connect to Redis at {self.redis_url}: {e}")
            logger.warning("Event publishing will be disabled.")
            self.enabled = False
            self.redis_client = None
    
    def publish(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        channel: Optional[str] = None
    ) -> bool:
        """
        Publish an event to Redis.
        
        Args:
            event_type: Type of event (e.g., "paper.added", "sync.completed")
            data: Event data dictionary
            channel: Redis channel to publish to. Defaults to event_type
            
        Returns:
            True if event was published successfully, False otherwise
        """
        if not self.enabled or not self.redis_client:
            logger.debug(f"Event publishing disabled. Would publish {event_type}: {data}")
            return False
        
        try:
            # Generate unique event ID
            event_id = str(uuid.uuid4())
            
            # Create base event structure
            event = {
                "event_type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "service": self.service_name,
                "event_id": event_id,
                **data
            }
            
            # Use event_type as channel if not specified
            target_channel = channel or event_type
            
            # Publish to Redis
            message = json.dumps(event)
            result = self.redis_client.publish(target_channel, message)
            
            logger.debug(f"Published event {event_type} to channel {target_channel}")
            logger.debug(f"Event data: {event}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")
            return False
    
    def publish_paper_event(
        self,
        event_type: str,
        paper_id: int,
        paper_title: Optional[str] = None,
        user_id: Optional[str] = None,
        changes: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish a paper-related event.
        
        Args:
            event_type: Type of event ("paper.added", "paper.updated", "paper.deleted")
            paper_id: ID of the paper
            paper_title: Title of the paper
            user_id: ID of user who performed the action
            changes: List of changed fields (for updates)
            metadata: Additional metadata
            
        Returns:
            True if event was published successfully
        """
        data = {
            "paper_id": paper_id,
            "paper_title": paper_title,
            "user_id": user_id,
            "changes": changes,
            "metadata": metadata
        }
        
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        return self.publish(event_type, data)
    
    def publish_sync_event(
        self,
        event_type: str,
        sync_id: str,
        sync_type: str = "zotero",
        results: Optional[Dict[str, Any]] = None,
        duration_seconds: Optional[int] = None,
        papers_processed: Optional[int] = None
    ) -> bool:
        """
        Publish a sync-related event.
        
        Args:
            event_type: Type of event ("sync.started", "sync.completed", "sync.failed")
            sync_id: ID of the sync operation
            sync_type: Type of sync ("zotero", "manual", etc.)
            results: Sync results dictionary
            duration_seconds: Duration of sync operation
            papers_processed: Number of papers processed
            
        Returns:
            True if event was published successfully
        """
        data = {
            "sync_id": sync_id,
            "sync_type": sync_type,
            "results": results,
            "duration_seconds": duration_seconds,
            "papers_processed": papers_processed
        }
        
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        return self.publish(event_type, data)
    
    def publish_paper_added(
        self,
        paper_id: int,
        paper_title: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Publish paper.added event."""
        return self.publish_paper_event(
            "paper.added",
            paper_id=paper_id,
            paper_title=paper_title,
            user_id=user_id,
            metadata=metadata
        )
    
    def publish_paper_updated(
        self,
        paper_id: int,
        paper_title: str,
        changes: List[str],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Publish paper.updated event."""
        return self.publish_paper_event(
            "paper.updated",
            paper_id=paper_id,
            paper_title=paper_title,
            user_id=user_id,
            changes=changes,
            metadata=metadata
        )
    
    def publish_paper_deleted(
        self,
        paper_id: int,
        paper_title: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Publish paper.deleted event."""
        return self.publish_paper_event(
            "paper.deleted",
            paper_id=paper_id,
            paper_title=paper_title,
            user_id=user_id,
            metadata=metadata
        )
    
    def publish_sync_completed(
        self,
        sync_id: str,
        results: Dict[str, Any],
        duration_seconds: int,
        papers_processed: int = 0,
        sync_type: str = "zotero"
    ) -> bool:
        """Publish sync.completed event."""
        return self.publish_sync_event(
            "sync.completed",
            sync_id=sync_id,
            sync_type=sync_type,
            results=results,
            duration_seconds=duration_seconds,
            papers_processed=papers_processed
        )
    
    def is_connected(self) -> bool:
        """Check if Redis connection is available."""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information."""
        return {
            "redis_url": self.redis_url,
            "service_name": self.service_name,
            "enabled": self.enabled,
            "connected": self.is_connected() if self.enabled else False,
            "redis_available": REDIS_AVAILABLE
        }


# Global event publisher instance
_event_publisher: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    """Get the global event publisher instance."""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher()
    return _event_publisher


def publish_paper_added(paper_id: int, paper_title: str, user_id: Optional[str] = None) -> bool:
    """Convenience function to publish paper.added event."""
    return get_event_publisher().publish_paper_added(paper_id, paper_title, user_id)


def publish_paper_updated(
    paper_id: int, 
    paper_title: str, 
    changes: List[str], 
    user_id: Optional[str] = None
) -> bool:
    """Convenience function to publish paper.updated event."""
    return get_event_publisher().publish_paper_updated(paper_id, paper_title, changes, user_id)


def publish_paper_deleted(paper_id: int, paper_title: str, user_id: Optional[str] = None) -> bool:
    """Convenience function to publish paper.deleted event."""
    return get_event_publisher().publish_paper_deleted(paper_id, paper_title, user_id)


def publish_sync_completed(
    sync_id: str, 
    results: Dict[str, Any], 
    duration_seconds: int, 
    papers_processed: int = 0
) -> bool:
    """Convenience function to publish sync.completed event."""
    return get_event_publisher().publish_sync_completed(
        sync_id, results, duration_seconds, papers_processed
    )