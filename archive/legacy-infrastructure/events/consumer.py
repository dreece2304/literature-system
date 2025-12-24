"""
Redis event consumer for paper events from literature-database.

This module listens to paper.added and paper.updated events and automatically
generates embeddings for new/updated papers.
"""

import json
import asyncio
import signal
from typing import Optional, Dict, Any
from datetime import datetime

import redis.asyncio as redis
import httpx
from loguru import logger

from config.settings import settings
from src.embeddings.generator import get_embedding_generator
from src.embeddings.chunker import get_text_chunker
from src.embeddings.vectorstore import get_vector_store


class PaperEventConsumer:
    """
    Consumes paper events from Redis pub/sub.

    Features:
    - Automatic embedding generation for new papers
    - Update handling for modified papers
    - Graceful shutdown
    - Error handling and retry logic
    - Event statistics tracking
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        channel: Optional[str] = None,
        litdb_api_url: Optional[str] = None,
    ):
        """
        Initialize the event consumer.

        Args:
            redis_url: Redis connection URL (default: from settings)
            channel: Redis channel to subscribe to (default: from settings)
            litdb_api_url: Literature database API URL (default: from settings)
        """
        self.redis_url = redis_url or settings.redis.url
        self.channel = channel or settings.redis.paper_events_channel
        self.litdb_api_url = litdb_api_url or settings.litdb.api_url

        # Components (lazy-loaded)
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._http_client: Optional[httpx.AsyncClient] = None

        # Lazy-load these singletons
        self._generator = None
        self._chunker = None
        self._vectorstore = None

        # State
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Statistics
        self.stats = {
            "events_received": 0,
            "papers_processed": 0,
            "papers_failed": 0,
            "embeddings_generated": 0,
            "started_at": None,
        }

        logger.info(
            f"PaperEventConsumer initialized: channel={self.channel}, "
            f"api_url={self.litdb_api_url}"
        )

    async def _ensure_components(self):
        """Lazy-load all components."""
        if self._generator is None:
            self._generator = get_embedding_generator()
            self._chunker = get_text_chunker()
            self._vectorstore = get_vector_store()
            logger.info("Loaded embedding components")

        if self._redis is None:
            self._redis = await redis.from_url(self.redis_url)
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(self.channel)
            logger.info(f"Connected to Redis and subscribed to {self.channel}")

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=settings.litdb.timeout,
                base_url=self.litdb_api_url,
            )
            logger.info(f"HTTP client initialized for {self.litdb_api_url}")

    async def start(self):
        """Start consuming events."""
        if self._running:
            logger.warning("Consumer already running")
            return

        self._running = True
        self.stats["started_at"] = datetime.utcnow().isoformat()

        logger.info("Starting PaperEventConsumer...")

        try:
            await self._ensure_components()
            await self._consume_loop()
        except Exception as e:
            logger.error(f"Fatal error in consumer: {e}")
            raise
        finally:
            await self.stop()

    async def _consume_loop(self):
        """Main event consumption loop."""
        logger.info("Event consumer loop started")

        while self._running:
            try:
                # Check for shutdown
                if self._shutdown_event.is_set():
                    logger.info("Shutdown event received")
                    break

                # Get message with timeout
                message = await asyncio.wait_for(
                    self._pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0,
                )

                if message and message["type"] == "message":
                    await self._handle_message(message)

            except asyncio.TimeoutError:
                # Normal - just checking for shutdown
                continue
            except Exception as e:
                logger.error(f"Error in consume loop: {e}")
                await asyncio.sleep(1)  # Brief pause before retry

        logger.info("Event consumer loop stopped")

    async def _handle_message(self, message: Dict):
        """
        Handle a single Redis message.

        Args:
            message: Redis pub/sub message
        """
        self.stats["events_received"] += 1

        try:
            # Parse event data
            data = json.loads(message["data"])
            event_type = data.get("event")
            paper_id = data.get("paper_id")

            logger.info(f"Received event: {event_type} for paper {paper_id}")

            if not paper_id:
                logger.warning(f"Event missing paper_id: {data}")
                return

            # Handle different event types
            if event_type in ["paper.added", "paper.updated"]:
                await self._process_paper(paper_id, event_type)
            else:
                logger.debug(f"Ignoring event type: {event_type}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse event JSON: {e}")
            self.stats["papers_failed"] += 1
        except Exception as e:
            logger.error(f"Failed to handle message: {e}")
            self.stats["papers_failed"] += 1

    async def _process_paper(self, paper_id: str, event_type: str):
        """
        Process a paper event by generating embeddings.

        Args:
            paper_id: ID of the paper to process
            event_type: Type of event (paper.added or paper.updated)
        """
        try:
            # Fetch paper data from literature-database
            logger.debug(f"Fetching paper {paper_id} from API")
            paper_data = await self._fetch_paper(paper_id)

            if not paper_data:
                logger.warning(f"Paper {paper_id} not found in database")
                self.stats["papers_failed"] += 1
                return

            # Generate embeddings
            logger.info(f"Generating embeddings for paper {paper_id}")
            await self._generate_and_store_embeddings(paper_data, event_type)

            self.stats["papers_processed"] += 1
            logger.info(f"Successfully processed paper {paper_id}")

        except Exception as e:
            logger.error(f"Failed to process paper {paper_id}: {e}")
            self.stats["papers_failed"] += 1

    async def _fetch_paper(self, paper_id: str) -> Optional[Dict]:
        """
        Fetch paper data from literature-database API.

        Args:
            paper_id: ID of paper to fetch

        Returns:
            Paper data dictionary or None if not found
        """
        try:
            response = await self._http_client.get(f"/papers/{paper_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Paper {paper_id} not found (404)")
                return None
            logger.error(f"HTTP error fetching paper {paper_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching paper {paper_id}: {e}")
            raise

    async def _generate_and_store_embeddings(
        self,
        paper_data: Dict,
        event_type: str,
    ):
        """
        Generate embeddings for a paper and store in vector database.

        Args:
            paper_data: Paper metadata and content
            event_type: Type of event (for update handling)
        """
        paper_id = paper_data.get("id") or paper_data.get("paper_id")

        # Chunk the paper
        chunks = self._chunker.chunk_paper(
            paper_data,
            fields=["title", "abstract", "full_text"],
        )

        if not chunks:
            logger.warning(f"No chunks generated for paper {paper_id}")
            return

        logger.debug(f"Generated {len(chunks)} chunks for paper {paper_id}")

        # Generate embeddings (run in thread pool to avoid blocking)
        loop = asyncio.get_event_loop()
        chunk_texts = [chunk.text for chunk in chunks]

        embeddings = await loop.run_in_executor(
            None,
            self._generator.generate,
            chunk_texts,
            None,  # batch_size (use default)
            False,  # show_progress
        )

        logger.debug(f"Generated {len(embeddings)} embeddings")

        # If updating, delete old embeddings first
        if event_type == "paper.updated":
            await self._delete_paper_embeddings(paper_id)

        # Store in vector database
        ids = [f"{paper_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [chunk.metadata for chunk in chunks]
        documents = [chunk.text for chunk in chunks]

        # Run synchronous vectorstore operation in executor
        await loop.run_in_executor(
            None,
            self._vectorstore.add_batch,
            ids,
            embeddings,
            metadatas,
            documents,
        )

        self.stats["embeddings_generated"] += len(embeddings)
        logger.info(f"Stored {len(embeddings)} embeddings for paper {paper_id}")

    async def _delete_paper_embeddings(self, paper_id: str):
        """
        Delete existing embeddings for a paper.

        Args:
            paper_id: ID of paper whose embeddings to delete
        """
        try:
            # Get existing embeddings for this paper
            loop = asyncio.get_event_loop()
            existing = await loop.run_in_executor(
                None,
                self._vectorstore.get,
                None,  # ids
                {"paper_id": paper_id},  # where filter
                None,  # limit
                [],  # include (just IDs)
            )

            if existing:
                ids = [item["id"] for item in existing]
                await loop.run_in_executor(
                    None,
                    self._vectorstore.delete,
                    ids,
                )
                logger.debug(f"Deleted {len(ids)} old embeddings for paper {paper_id}")

        except Exception as e:
            logger.warning(f"Failed to delete old embeddings for {paper_id}: {e}")
            # Non-fatal, continue anyway

    async def stop(self):
        """Stop the consumer gracefully."""
        if not self._running:
            return

        logger.info("Stopping PaperEventConsumer...")
        self._running = False
        self._shutdown_event.set()

        # Close connections
        if self._pubsub:
            await self._pubsub.unsubscribe(self.channel)
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        if self._http_client:
            await self._http_client.aclose()

        logger.info("PaperEventConsumer stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        stats = self.stats.copy()

        if stats["started_at"]:
            uptime = (
                datetime.utcnow()
                - datetime.fromisoformat(stats["started_at"])
            ).total_seconds()
            stats["uptime_seconds"] = uptime

        return stats

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check.

        Returns:
            Health status dictionary
        """
        health = {
            "status": "healthy" if self._running else "stopped",
            "running": self._running,
            "redis_connected": False,
            "http_client_ready": False,
        }

        try:
            if self._redis:
                await self._redis.ping()
                health["redis_connected"] = True
        except Exception as e:
            health["redis_error"] = str(e)

        if self._http_client:
            health["http_client_ready"] = True

        health["stats"] = self.get_stats()

        return health


async def run_consumer():
    """
    Main entry point to run the consumer.

    Handles signals for graceful shutdown.
    """
    consumer = PaperEventConsumer()

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        asyncio.create_task(consumer.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await consumer.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Consumer failed: {e}")
        raise
    finally:
        await consumer.stop()


if __name__ == "__main__":
    # Configure logging
    logger.add(
        settings.logging.log_file,
        rotation=settings.logging.rotation,
        retention=settings.logging.retention,
        level=settings.logging.level,
    )

    # Run the consumer
    asyncio.run(run_consumer())
