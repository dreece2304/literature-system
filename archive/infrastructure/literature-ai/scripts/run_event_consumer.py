#!/usr/bin/env python3
"""
Standalone event consumer for paper events.

Listens to Redis pub/sub for paper.added/paper.updated events
and automatically generates embeddings.
"""

import asyncio
import signal

from loguru import logger

from config.settings import settings, LOGS_DIR
from src.events.consumer import PaperEventConsumer


async def main():
    """Run the event consumer."""
    # Configure logging
    logger.remove()
    logger.add(
        LOGS_DIR / "event-consumer.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level="INFO",
        rotation="10 MB",
        retention="7 days",
    )

    logger.info("=" * 60)
    logger.info("Starting Paper Event Consumer")
    logger.info("=" * 60)
    logger.info(f"Redis URL: {settings.redis.url}")
    logger.info(f"Channel: {settings.redis.paper_events_channel}")
    logger.info(f"Literature DB API: {settings.litdb.api_url}")
    logger.info("=" * 60)

    # Create consumer
    consumer = PaperEventConsumer()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(consumer.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start consumer
    try:
        await consumer.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
        return 1
    finally:
        logger.info("Consumer stopped")
        logger.info("Final statistics:")
        logger.info(f"  Events received: {consumer.stats['events_received']}")
        logger.info(f"  Papers processed: {consumer.stats['papers_processed']}")
        logger.info(f"  Papers failed: {consumer.stats['papers_failed']}")
        logger.info(f"  Embeddings generated: {consumer.stats['embeddings_generated']}")

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
