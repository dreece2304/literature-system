#!/usr/bin/env python3
"""Test script for event publishing functionality."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_event_service():
    """Test event service basic functionality."""
    print("Testing Event Publishing Service")
    print("=" * 40)

    try:
        from src.services.event_service import EventPublisher

        # Test initialization
        publisher = EventPublisher()
        print("✓ EventPublisher initialized")

        # Test connection info
        info = publisher.get_connection_info()
        print(f"✓ Connection info: {info}")

        # Test basic event publishing (will log if Redis not available)
        success = publisher.publish_paper_added(
            paper_id=1,
            paper_title="Test Paper",
            metadata={"test": True}
        )
        print(f"✓ Paper added event published: {success}")

        # Test sync event
        success = publisher.publish_sync_completed(
            sync_id="test_sync_123",
            results={"papers_added": 1, "errors": 0},
            duration_seconds=5,
            papers_processed=1
        )
        print(f"✓ Sync completed event published: {success}")

        print("\n✅ Event service tests completed successfully!")

    except Exception as e:
        print(f"❌ Error testing event service: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_shared_types():
    """Test shared types import."""
    print("\nTesting Shared Types")
    print("=" * 40)

    try:
        # Test shared types import
        import sys
        from pathlib import Path
        # Shared types are in monorepo root: research/shared/types/
        shared_path = str(Path(__file__).parent.parent.parent.parent / "shared")
        sys.path.insert(0, shared_path)

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "api_contracts",
            Path(shared_path) / "types" / "api_contracts.py"
        )
        api_contracts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api_contracts)

        # Test event types
        PaperEvent = api_contracts.PaperEvent
        SyncEvent = api_contracts.SyncEvent

        print(f"✓ PaperEvent class: {PaperEvent.__name__}")
        print(f"✓ SyncEvent class: {SyncEvent.__name__}")

        print("\n✅ Shared types tests completed successfully!")

    except Exception as e:
        print(f"❌ Error testing shared types: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    print("Literature Database Event Publishing Tests")
    print("=" * 50)

    try:
        # Test shared types
        test_shared_types()

        # Test event service
        test_event_service()

        print("\n" + "=" * 50)
        print("All tests passed! Event publishing is ready.")
        print("\nTo use with Redis:")
        print("  1. Install Redis: pip install redis")
        print("  2. Start Redis server: redis-server")
        print("  3. Set REDIS_URL environment variable (optional)")
        print("     export REDIS_URL=redis://localhost:6379")
        print("  4. Start the service: python run_service.py")
        sys.exit(0)
    except Exception:
        print("\n" + "=" * 50)
        print("Some tests failed. Check the errors above.")
        sys.exit(1)
