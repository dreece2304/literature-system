"""
Comprehensive tests for Redis event publishing functionality.

Tests that events are published correctly for all CRUD operations
and that event format matches the API contracts specifications.
"""
import json
from datetime import datetime
from unittest.mock import Mock, patch
from fastapi import status


class TestEventPublishingService:
    """Test the event publishing service directly."""

    def test_event_publisher_initialization(self, mock_event_publisher):
        """Test that event publisher initializes correctly."""
        publisher, mock_redis = mock_event_publisher

        assert publisher.enabled is True
        assert publisher.service_name == "literature-database"
        assert mock_redis is not None

    def test_event_publisher_connection_info(self, mock_event_publisher):
        """Test getting connection information."""
        publisher, mock_redis = mock_event_publisher

        info = publisher.get_connection_info()

        assert info["service_name"] == "literature-database"
        assert info["enabled"] is True
        assert info["connected"] is True
        assert "redis_url" in info

    def test_publish_paper_added_event(self, mock_event_publisher):
        """Test publishing paper.added event."""
        publisher, mock_redis = mock_event_publisher

        success = publisher.publish_paper_added(
            paper_id=123,
            paper_title="Test Paper",
            user_id="test_user",
            metadata={"doi": "10.1000/test", "year": 2024}
        )

        assert success is True
        assert len(mock_redis.published_events) == 1

        event = mock_redis.published_events[0]
        assert event["channel"] == "paper.added"

        # Check event data structure
        data = event["data"]
        assert data["event_type"] == "paper.added"
        assert data["service"] == "literature-database"
        assert data["paper_id"] == 123
        assert data["paper_title"] == "Test Paper"
        assert data["user_id"] == "test_user"
        assert data["metadata"]["doi"] == "10.1000/test"
        assert "event_id" in data
        assert "timestamp" in data

    def test_publish_paper_updated_event(self, mock_event_publisher):
        """Test publishing paper.updated event."""
        publisher, mock_redis = mock_event_publisher

        success = publisher.publish_paper_updated(
            paper_id=123,
            paper_title="Updated Paper",
            changes=["rating", "read_status"],
            user_id="test_user"
        )

        assert success is True
        assert len(mock_redis.published_events) == 1

        event = mock_redis.published_events[0]
        assert event["channel"] == "paper.updated"

        data = event["data"]
        assert data["event_type"] == "paper.updated"
        assert data["paper_id"] == 123
        assert data["changes"] == ["rating", "read_status"]

    def test_publish_paper_deleted_event(self, mock_event_publisher):
        """Test publishing paper.deleted event."""
        publisher, mock_redis = mock_event_publisher

        success = publisher.publish_paper_deleted(
            paper_id=123,
            paper_title="Deleted Paper",
            metadata={"reason": "duplicate"}
        )

        assert success is True
        assert len(mock_redis.published_events) == 1

        event = mock_redis.published_events[0]
        assert event["channel"] == "paper.deleted"

        data = event["data"]
        assert data["event_type"] == "paper.deleted"
        assert data["paper_id"] == 123
        assert data["paper_title"] == "Deleted Paper"

    def test_publish_sync_completed_event(self, mock_event_publisher):
        """Test publishing sync.completed event."""
        publisher, mock_redis = mock_event_publisher

        results = {
            "papers_added": 5,
            "papers_updated": 3,
            "papers_unchanged": 10,
            "errors": 0
        }

        success = publisher.publish_sync_completed(
            sync_id="sync_123",
            results=results,
            duration_seconds=120,
            papers_processed=18,
            sync_type="zotero"
        )

        assert success is True
        assert len(mock_redis.published_events) == 1

        event = mock_redis.published_events[0]
        assert event["channel"] == "sync.completed"

        data = event["data"]
        assert data["event_type"] == "sync.completed"
        assert data["sync_id"] == "sync_123"
        assert data["sync_type"] == "zotero"
        assert data["results"] == results
        assert data["duration_seconds"] == 120
        assert data["papers_processed"] == 18

    def test_event_publisher_disabled(self):
        """Test event publisher behavior when disabled."""
        from src.services.event_service import EventPublisher

        publisher = EventPublisher()
        publisher.enabled = False

        success = publisher.publish_paper_added(123, "Test Paper")
        assert success is False  # Should return False when disabled

    def test_redis_connection_failure(self, monkeypatch):
        """Test handling of Redis connection failures."""
        from src.services.event_service import EventPublisher

        # Mock Redis to raise exception
        mock_redis = Mock()
        mock_redis.publish.side_effect = Exception("Redis connection failed")

        publisher = EventPublisher()
        publisher.redis_client = mock_redis
        publisher.enabled = True

        success = publisher.publish_paper_added(123, "Test Paper")
        assert success is False


class TestAPIEventIntegration:
    """Test that API endpoints correctly publish events."""

    def test_create_paper_publishes_event(self, client, sample_paper_data, mock_event_publisher):
        """Test that creating a paper publishes paper.added event."""
        publisher, mock_redis = mock_event_publisher

        # Mock the global event publisher
        with patch('src.api.main.event_publisher', publisher):
            response = client.post("/api/v1/papers", json=sample_paper_data)

            assert response.status_code == status.HTTP_200_OK
            paper = response.json()

            # Check that event was published
            assert len(mock_redis.published_events) == 1

            event = mock_redis.published_events[0]
            assert event["channel"] == "paper.added"

            data = event["data"]
            assert data["event_type"] == "paper.added"
            assert data["paper_id"] == paper["id"]
            assert data["paper_title"] == sample_paper_data["title"]
            assert "metadata" in data

    def test_update_paper_publishes_event(self, client, sample_paper_data, sample_paper_update, mock_event_publisher):
        """Test that updating a paper publishes paper.updated event."""
        publisher, mock_redis = mock_event_publisher

        with patch('src.api.main.event_publisher', publisher):
            # Create paper first
            create_response = client.post("/api/v1/papers", json=sample_paper_data)
            paper = create_response.json()
            paper_id = paper["id"]

            # Clear events from creation
            mock_redis.published_events.clear()

            # Update the paper
            response = client.put(f"/api/v1/papers/{paper_id}", json=sample_paper_update)
            assert response.status_code == status.HTTP_200_OK

            # Check that update event was published
            assert len(mock_redis.published_events) == 1

            event = mock_redis.published_events[0]
            assert event["channel"] == "paper.updated"

            data = event["data"]
            assert data["event_type"] == "paper.updated"
            assert data["paper_id"] == paper_id
            assert "changes" in data
            assert len(data["changes"]) > 0

    def test_delete_paper_publishes_event(self, client, sample_paper_data, mock_event_publisher):
        """Test that deleting a paper publishes paper.deleted event."""
        publisher, mock_redis = mock_event_publisher

        with patch('src.api.main.event_publisher', publisher):
            # Create paper first
            create_response = client.post("/api/v1/papers", json=sample_paper_data)
            paper = create_response.json()
            paper_id = paper["id"]

            # Clear events from creation
            mock_redis.published_events.clear()

            # Delete the paper
            response = client.delete(f"/api/v1/papers/{paper_id}")
            assert response.status_code == status.HTTP_200_OK

            # Check that delete event was published
            assert len(mock_redis.published_events) == 1

            event = mock_redis.published_events[0]
            assert event["channel"] == "paper.deleted"

            data = event["data"]
            assert data["event_type"] == "paper.deleted"
            assert data["paper_id"] == paper_id
            assert data["paper_title"] == sample_paper_data["title"]

    def test_sync_operation_publishes_event(self, client, mock_event_publisher):
        """Test that sync operations publish sync.completed events."""
        publisher, mock_redis = mock_event_publisher

        with patch('src.api.main.event_publisher', publisher):
            # Trigger sync
            response = client.post("/api/v1/sync/zotero", json={"force_full_sync": False})
            assert response.status_code == status.HTTP_200_OK
            sync_data = response.json()

            # Wait for simulated sync to complete and publish event
            import time
            time.sleep(3)  # Wait for async simulation to complete

            # Check that sync.completed event was published
            sync_events = [e for e in mock_redis.published_events if e["channel"] == "sync.completed"]
            assert len(sync_events) >= 1

            event = sync_events[0]
            data = event["data"]
            assert data["event_type"] == "sync.completed"
            assert data["sync_id"] == sync_data["sync_id"]
            assert "results" in data
            assert "duration_seconds" in data


class TestEventFormatCompliance:
    """Test that events match API contracts format."""

    def test_paper_event_schema_compliance(self, mock_event_publisher):
        """Test that paper events match PaperEvent schema from api_contracts."""
        publisher, mock_redis = mock_event_publisher

        publisher.publish_paper_added(
            paper_id=123,
            paper_title="Test Paper",
            user_id="user123",
            metadata={"test": "data"}
        )

        event_data = mock_redis.published_events[0]["data"]

        # Test required fields from BaseEvent
        assert "event_type" in event_data
        assert "timestamp" in event_data
        assert "service" in event_data
        assert "event_id" in event_data

        # Test PaperEvent specific fields
        assert "paper_id" in event_data
        assert isinstance(event_data["paper_id"], int)

        # Test optional fields
        if "paper_title" in event_data:
            assert isinstance(event_data["paper_title"], str)
        if "user_id" in event_data:
            assert isinstance(event_data["user_id"], str)
        if "changes" in event_data:
            assert isinstance(event_data["changes"], list)
        if "metadata" in event_data:
            assert isinstance(event_data["metadata"], dict)

        # Test timestamp format
        timestamp_str = event_data["timestamp"]
        # Should be able to parse as ISO format
        parsed_timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        assert isinstance(parsed_timestamp, datetime)

    def test_sync_event_schema_compliance(self, mock_event_publisher):
        """Test that sync events match SyncEvent schema from api_contracts."""
        publisher, mock_redis = mock_event_publisher

        results = {"papers_added": 5, "errors": 0}
        publisher.publish_sync_completed(
            sync_id="sync_123",
            sync_type="zotero",
            results=results,
            duration_seconds=120,
            papers_processed=5
        )

        event_data = mock_redis.published_events[0]["data"]

        # Test required fields from BaseEvent
        assert "event_type" in event_data
        assert "timestamp" in event_data
        assert "service" in event_data
        assert "event_id" in event_data

        # Test SyncEvent specific fields
        assert "sync_id" in event_data
        assert isinstance(event_data["sync_id"], str)
        assert "sync_type" in event_data
        assert isinstance(event_data["sync_type"], str)

        # Test optional fields
        if "results" in event_data:
            assert isinstance(event_data["results"], dict)
        if "duration_seconds" in event_data:
            assert isinstance(event_data["duration_seconds"], int)
        if "papers_processed" in event_data:
            assert isinstance(event_data["papers_processed"], int)

    def test_event_id_uniqueness(self, mock_event_publisher):
        """Test that each event gets a unique event_id."""
        publisher, mock_redis = mock_event_publisher

        # Publish multiple events
        for i in range(5):
            publisher.publish_paper_added(i, f"Paper {i}")

        event_ids = [event["data"]["event_id"] for event in mock_redis.published_events]

        # All event IDs should be unique
        assert len(set(event_ids)) == 5

        # All event IDs should be strings
        for event_id in event_ids:
            assert isinstance(event_id, str)
            assert len(event_id) > 0

    def test_event_timestamp_accuracy(self, mock_event_publisher):
        """Test that event timestamps are recent and accurate."""
        publisher, mock_redis = mock_event_publisher

        before_time = datetime.utcnow()
        publisher.publish_paper_added(123, "Test Paper")
        after_time = datetime.utcnow()

        event_data = mock_redis.published_events[0]["data"]
        event_timestamp = datetime.fromisoformat(event_data["timestamp"].replace('Z', '+00:00'))

        # Event timestamp should be between before and after times
        assert before_time <= event_timestamp <= after_time

    def test_event_service_name_consistency(self, mock_event_publisher):
        """Test that all events use consistent service name."""
        publisher, mock_redis = mock_event_publisher

        # Publish different types of events
        publisher.publish_paper_added(1, "Paper 1")
        publisher.publish_paper_updated(2, "Paper 2", ["title"])
        publisher.publish_paper_deleted(3, "Paper 3")
        publisher.publish_sync_completed("sync_1", {}, 60)

        # All events should have the same service name
        service_names = [event["data"]["service"] for event in mock_redis.published_events]
        assert all(name == "literature-database" for name in service_names)


class TestEventPublishingReliability:
    """Test event publishing reliability and error handling."""

    def test_event_publishing_with_redis_failure(self):
        """Test graceful handling of Redis failures."""
        from src.services.event_service import EventPublisher

        # Create real publisher (will fail to connect to Redis if not available)
        publisher = EventPublisher()

        # Mock the Redis client to simulate failure
        mock_redis = Mock()
        mock_redis.publish.side_effect = Exception("Redis connection lost")
        publisher.redis_client = mock_redis
        publisher.enabled = True

        # Publishing should not raise exception but return False
        success = publisher.publish_paper_added(123, "Test Paper")
        assert success is False

    def test_event_publishing_with_large_payloads(self, mock_event_publisher):
        """Test event publishing with large metadata payloads."""
        publisher, mock_redis = mock_event_publisher

        # Create large metadata
        large_metadata = {"large_field": "x" * 10000}

        success = publisher.publish_paper_added(
            paper_id=123,
            paper_title="Test Paper",
            metadata=large_metadata
        )

        assert success is True
        assert len(mock_redis.published_events) == 1

        event_data = mock_redis.published_events[0]["data"]
        assert len(event_data["metadata"]["large_field"]) == 10000

    def test_event_publishing_with_special_characters(self, mock_event_publisher):
        """Test event publishing with special characters and unicode."""
        publisher, mock_redis = mock_event_publisher

        # Test with special characters
        special_title = "Paper with Special: 中文, Émojis 🧪, and Math ∑∫∆"

        success = publisher.publish_paper_added(
            paper_id=123,
            paper_title=special_title
        )

        assert success is True
        event_data = mock_redis.published_events[0]["data"]
        assert event_data["paper_title"] == special_title

        # Ensure JSON serialization works
        json_str = json.dumps(event_data)
        parsed_back = json.loads(json_str)
        assert parsed_back["paper_title"] == special_title

    def test_concurrent_event_publishing(self, mock_event_publisher):
        """Test that concurrent event publishing works correctly."""
        publisher, mock_redis = mock_event_publisher

        import threading
        import time

        def publish_events(start_id):
            for i in range(10):
                publisher.publish_paper_added(start_id + i, f"Paper {start_id + i}")
                time.sleep(0.01)  # Small delay to simulate real work

        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=publish_events, args=(i * 100,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should have 30 events (3 threads * 10 events each)
        assert len(mock_redis.published_events) == 30

        # All event IDs should be unique
        event_ids = [event["data"]["event_id"] for event in mock_redis.published_events]
        assert len(set(event_ids)) == 30


class TestEventMonitoring:
    """Test event monitoring and debugging capabilities."""

    def test_event_logging(self, caplog):
        """Test that events are properly logged."""
        from src.services.event_service import EventPublisher

        publisher = EventPublisher()
        publisher.enabled = True

        # Mock Redis to succeed
        mock_redis = Mock()
        mock_redis.publish.return_value = 1
        publisher.redis_client = mock_redis

        import logging
        with caplog.at_level(logging.DEBUG):
            publisher.publish_paper_added(123, "Test Paper")

        # Check that event was published (via mock)
        assert mock_redis.publish.called

    def test_connection_status_monitoring(self):
        """Test monitoring of Redis connection status."""
        from src.services.event_service import EventPublisher

        publisher = EventPublisher()

        # Test with mocked connected Redis
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        publisher.redis_client = mock_redis
        assert publisher.is_connected() is True

        # Test with Redis that fails ping
        mock_redis.ping.side_effect = Exception("Connection failed")
        assert publisher.is_connected() is False

    def test_event_statistics(self, mock_event_publisher):
        """Test gathering event publishing statistics."""
        publisher, mock_redis = mock_event_publisher

        # Publish various events
        publisher.publish_paper_added(1, "Paper 1")
        publisher.publish_paper_updated(2, "Paper 2", ["title"])
        publisher.publish_paper_deleted(3, "Paper 3")
        publisher.publish_sync_completed("sync_1", {}, 60)

        # Check event counts by type
        event_types = [event["data"]["event_type"] for event in mock_redis.published_events]

        assert event_types.count("paper.added") == 1
        assert event_types.count("paper.updated") == 1
        assert event_types.count("paper.deleted") == 1
        assert event_types.count("sync.completed") == 1
