"""
Client for literature-database API.

Provides a high-level interface for interacting with the literature-database
to fetch papers and store extracted content.
"""

from typing import Optional, Dict, Any, List
import httpx
from loguru import logger

from config.settings import settings


class DatabaseClient:
    """
    Client for literature-database REST API.

    Features:
    - Fetch paper metadata and content
    - Store extracted content
    - Manage project relevance
    - Get extraction queue
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
    ):
        """
        Initialize database client.

        Args:
            base_url: Literature database API URL (default: from settings)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or settings.litdb.api_url
        self.timeout = timeout

        # HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
        )

        logger.info(f"DatabaseClient initialized: {self.base_url}")

    async def get_paper(self, paper_id: int) -> Optional[Dict[str, Any]]:
        """
        Get paper by ID.

        Args:
            paper_id: Paper ID

        Returns:
            Paper data or None if not found
        """
        try:
            response = await self.client.get(f"/papers/{paper_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get paper {paper_id}: {e}")
            raise

    async def get_paper_content_for_extraction(self, paper_id: int) -> Optional[Dict[str, Any]]:
        """
        Get full paper content for AI processing.

        Args:
            paper_id: Paper ID

        Returns:
            Paper content data or None if not found
        """
        try:
            response = await self.client.get(f"/integration/papers/{paper_id}/content")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get paper content {paper_id}: {e}")
            raise

    async def get_paper_extracted_content(self, paper_id: int) -> Optional[Dict[str, Any]]:
        """
        Get existing extracted content for a paper.

        Args:
            paper_id: Paper ID

        Returns:
            Extracted content or None if not extracted yet
        """
        try:
            response = await self.client.get(f"/papers/{paper_id}/content")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to get extracted content {paper_id}: {e}")
            raise

    async def store_extracted_content(
        self,
        paper_id: int,
        content: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Store extracted content for a paper.

        Args:
            paper_id: Paper ID
            content: Extracted content data

        Returns:
            Created content record
        """
        try:
            # Check if content already exists
            existing = await self.get_paper_extracted_content(paper_id)
            if existing:
                # Update existing
                response = await self.client.put(
                    f"/papers/{paper_id}/content",
                    json=content,
                )
            else:
                # Create new
                response = await self.client.post(
                    f"/papers/{paper_id}/content",
                    json=content,
                )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to store content for paper {paper_id}: {e}")
            raise

    async def get_paper_relevance(self, paper_id: int) -> List[Dict[str, Any]]:
        """
        Get all project relevances for a paper.

        Args:
            paper_id: Paper ID

        Returns:
            List of relevance records
        """
        try:
            response = await self.client.get(f"/papers/{paper_id}/relevance")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get relevances for paper {paper_id}: {e}")
            raise

    async def store_relevance(
        self,
        paper_id: int,
        project_name: str,
        overall_relevance: str,
        relevance_summary: Optional[str] = None,
        primary_use: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store project relevance for a paper.

        Args:
            paper_id: Paper ID
            project_name: Project name
            overall_relevance: CRITICAL, HIGH, MEDIUM, LOW, or NONE
            relevance_summary: Summary of why paper is relevant
            primary_use: Primary use in manuscript

        Returns:
            Created/updated relevance record
        """
        data = {
            "project_name": project_name,
            "overall_relevance": overall_relevance,
        }
        if relevance_summary:
            data["relevance_summary"] = relevance_summary
        if primary_use:
            data["primary_use"] = primary_use

        try:
            # Check if relevance already exists
            existing = await self.get_paper_relevance(paper_id)
            exists = any(r["project_name"] == project_name for r in existing)

            if exists:
                response = await self.client.put(
                    f"/papers/{paper_id}/relevance/{project_name}",
                    json=data,
                )
            else:
                response = await self.client.post(
                    f"/papers/{paper_id}/relevance",
                    json=data,
                )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to store relevance for paper {paper_id}: {e}")
            raise

    async def get_extraction_queue(self, limit: int = 50) -> Dict[str, Any]:
        """
        Get papers needing extraction.

        Args:
            limit: Maximum papers to return

        Returns:
            Extraction queue data
        """
        try:
            response = await self.client.get(f"/extraction/queue?limit={limit}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get extraction queue: {e}")
            raise

    async def get_extraction_stats(self) -> Dict[str, Any]:
        """
        Get extraction statistics.

        Returns:
            Extraction stats
        """
        try:
            response = await self.client.get("/extraction/stats")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get extraction stats: {e}")
            raise

    async def get_project_papers(
        self,
        project_name: str,
        min_relevance: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get papers relevant to a project.

        Args:
            project_name: Project name
            min_relevance: Minimum relevance level filter

        Returns:
            Project papers data
        """
        try:
            url = f"/projects/{project_name}/papers"
            if min_relevance:
                url += f"?min_relevance={min_relevance}"
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get project papers for {project_name}: {e}")
            raise

    async def health_check(self) -> Dict[str, Any]:
        """
        Check database API health.

        Returns:
            Health status
        """
        try:
            response = await self.client.get("/integration/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("DatabaseClient closed")


# Global singleton instance
_db_client: Optional[DatabaseClient] = None


def get_database_client() -> DatabaseClient:
    """
    Get global DatabaseClient instance (singleton).

    Returns:
        Shared DatabaseClient instance
    """
    global _db_client

    if _db_client is None:
        _db_client = DatabaseClient()

    return _db_client


async def reset_database_client():
    """Reset global database client (useful for testing)."""
    global _db_client
    if _db_client:
        await _db_client.close()
    _db_client = None
