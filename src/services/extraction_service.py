"""Extraction Service for AI-powered paper analysis.

Uses local LLM (Ollama with Qwen) or Claude API to extract structured
information from papers: summaries, key findings, methodology, topics.

Architecture:
    ExtractionService -> LLMClient (Ollama/Claude) -> LLM
                      -> PaperService -> Database
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal
from abc import ABC, abstractmethod

import httpx

from literature_core import get_session, get_logger, Paper, PaperContent
from config.ai_settings import settings

logger = get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExtractionStatus:
    """Status report for extraction coverage."""
    total_papers: int = 0
    papers_with_full_text: int = 0
    papers_with_abstract: int = 0
    papers_with_extraction: int = 0
    papers_needing_extraction: int = 0

    @property
    def extraction_coverage_percent(self) -> float:
        """Percentage of extractable papers that have been extracted."""
        extractable = self.papers_with_full_text or self.papers_with_abstract
        if extractable == 0:
            return 100.0
        return (self.papers_with_extraction / extractable) * 100


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""
    papers_processed: int = 0
    papers_extracted: int = 0
    papers_skipped: int = 0
    papers_error: int = 0
    errors: list[str] = field(default_factory=list)
    tokens_used: int = 0

    @property
    def success(self) -> bool:
        """True if at least some papers were processed without total failure."""
        return self.papers_processed > 0 or len(self.errors) == 0


@dataclass
class PaperExtraction:
    """Extracted content from a single paper."""
    paper_id: int
    paper_type: Optional[str] = None
    topics: Optional[list[str]] = None
    one_sentence_summary: Optional[str] = None
    key_findings: Optional[list[str]] = None
    methodology_summary: Optional[str] = None
    extractor_model: Optional[str] = None
    success: bool = False
    error: Optional[str] = None


# =============================================================================
# LLM Client Abstraction
# =============================================================================

class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def extract(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str] = None
    ) -> PaperExtraction:
        """Extract structured content from a paper."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM is available."""
        pass


class OllamaClient(LLMClient):
    """Ollama client for local LLM inference."""

    EXTRACTION_PROMPT = """You are an expert research paper analyst. \
Extract structured information from this paper.

PAPER TITLE: {title}

ABSTRACT: {abstract}

{full_text_section}

Extract the following in JSON format:
{{
    "paper_type": "research_article|review|conference|preprint|thesis|other",
    "topics": ["topic1", "topic2", "topic3"],
    "one_sentence_summary": "A single sentence summarizing the main contribution",
    "key_findings": ["finding1", "finding2", "finding3"],
    "methodology_summary": "Brief description of methods used (2-3 sentences)"
}}

Respond ONLY with valid JSON, no other text."""

    def __init__(self):
        self.host = settings.ollama.host
        self.model = settings.ollama.reader_model
        self.timeout = settings.ollama.timeout
        self.temperature = settings.ollama.reader_temperature

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def extract(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str] = None,
        paper_id: int = 0
    ) -> PaperExtraction:
        """Extract structured content using Ollama."""
        # Prepare prompt
        full_text_section = ""
        if full_text:
            # Truncate to ~4000 chars to fit context
            truncated = full_text[:4000] if len(full_text) > 4000 else full_text
            full_text_section = f"FULL TEXT (excerpt):\n{truncated}\n"

        prompt = self.EXTRACTION_PROMPT.format(
            title=title,
            abstract=abstract or "Not available",
            full_text_section=full_text_section
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": 1024,
                        }
                    }
                )

                if response.status_code != 200:
                    return PaperExtraction(
                        paper_id=paper_id,
                        success=False,
                        error=f"Ollama error: {response.status_code}"
                    )

                data = response.json()
                response_text = data.get("response", "")

                # Parse JSON from response
                extraction = self._parse_extraction(response_text, paper_id)
                extraction.extractor_model = f"ollama/{self.model}"
                return extraction

        except httpx.TimeoutException:
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error="Ollama timeout"
            )
        except Exception as e:
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=str(e)
            )

    def _parse_extraction(self, text: str, paper_id: int) -> PaperExtraction:
        """Parse JSON extraction from LLM response."""
        try:
            # Try to find JSON in response
            text = text.strip()

            # Handle markdown code blocks
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()

            # Handle potential leading/trailing text
            brace_start = text.find("{")
            brace_end = text.rfind("}") + 1
            if brace_start >= 0 and brace_end > brace_start:
                text = text[brace_start:brace_end]

            data = json.loads(text)

            return PaperExtraction(
                paper_id=paper_id,
                paper_type=data.get("paper_type"),
                topics=data.get("topics", []),
                one_sentence_summary=data.get("one_sentence_summary"),
                key_findings=data.get("key_findings", []),
                methodology_summary=data.get("methodology_summary"),
                success=True
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction JSON: {e}")
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=f"JSON parse error: {e}"
            )


class ClaudeClient(LLMClient):
    """Anthropic Claude API client for extraction."""

    EXTRACTION_PROMPT = """Extract structured information from this research paper.

PAPER TITLE: {title}

ABSTRACT: {abstract}

{full_text_section}

Return a JSON object with:
- paper_type: one of "research_article", "review", "conference", "preprint", "thesis", "other"
- topics: array of 3-5 key topics/themes
- one_sentence_summary: single sentence capturing the main contribution
- key_findings: array of 3-5 key findings or results
- methodology_summary: 2-3 sentences describing the methods used

Return ONLY the JSON object, no other text."""

    def __init__(self):
        self.api_key = settings.claude.api_key
        self.model = settings.claude.model
        self.max_tokens = settings.claude.max_tokens
        self.temperature = settings.claude.temperature
        self.timeout = settings.claude.timeout

    def is_available(self) -> bool:
        """Check if Claude API key is configured."""
        return bool(self.api_key)

    async def extract(
        self,
        title: str,
        abstract: str,
        full_text: Optional[str] = None,
        paper_id: int = 0
    ) -> PaperExtraction:
        """Extract structured content using Claude API."""
        if not self.api_key:
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error="Claude API key not configured"
            )

        # Prepare prompt
        full_text_section = ""
        if full_text:
            # Truncate to fit context (Claude has larger context)
            truncated = full_text[:8000] if len(full_text) > 8000 else full_text
            full_text_section = f"FULL TEXT (excerpt):\n{truncated}\n"

        prompt = self.EXTRACTION_PROMPT.format(
            title=title,
            abstract=abstract or "Not available",
            full_text_section=full_text_section
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )

                if response.status_code != 200:
                    return PaperExtraction(
                        paper_id=paper_id,
                        success=False,
                        error=f"Claude API error: {response.status_code}"
                    )

                data = response.json()
                response_text = data.get("content", [{}])[0].get("text", "")

                # Parse JSON from response
                extraction = self._parse_extraction(response_text, paper_id)
                extraction.extractor_model = f"claude/{self.model}"
                return extraction

        except Exception as e:
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=str(e)
            )

    def _parse_extraction(self, text: str, paper_id: int) -> PaperExtraction:
        """Parse JSON extraction from Claude response."""
        try:
            text = text.strip()

            # Handle markdown code blocks
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                text = text[start:end].strip()
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                text = text[start:end].strip()

            brace_start = text.find("{")
            brace_end = text.rfind("}") + 1
            if brace_start >= 0 and brace_end > brace_start:
                text = text[brace_start:brace_end]

            data = json.loads(text)

            return PaperExtraction(
                paper_id=paper_id,
                paper_type=data.get("paper_type"),
                topics=data.get("topics", []),
                one_sentence_summary=data.get("one_sentence_summary"),
                key_findings=data.get("key_findings", []),
                methodology_summary=data.get("methodology_summary"),
                success=True
            )

        except json.JSONDecodeError as e:
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=f"JSON parse error: {e}"
            )


# =============================================================================
# Extraction Service
# =============================================================================

class ExtractionService:
    """Service for AI-powered paper extraction."""

    # Default LLM preference order
    LLM_PREFERENCE = ["ollama", "claude"]

    @classmethod
    def get_extraction_status(cls) -> ExtractionStatus:
        """Get extraction coverage statistics.

        Returns:
            ExtractionStatus with coverage statistics
        """
        with get_session() as session:
            status = ExtractionStatus()

            status.total_papers = session.query(Paper).count()

            status.papers_with_full_text = session.query(Paper).filter(
                Paper.full_text.isnot(None),
                Paper.full_text != ''
            ).count()

            status.papers_with_abstract = session.query(Paper).filter(
                Paper.abstract.isnot(None),
                Paper.abstract != ''
            ).count()

            status.papers_with_extraction = session.query(PaperContent).count()

            # Papers needing extraction: have content but no extraction
            extractable_ids = session.query(Paper.id).filter(
                (Paper.full_text.isnot(None) & (Paper.full_text != '')) |
                (Paper.abstract.isnot(None) & (Paper.abstract != ''))
            ).subquery()

            extracted_ids = session.query(PaperContent.paper_id).subquery()

            status.papers_needing_extraction = session.query(Paper).filter(
                Paper.id.in_(extractable_ids),
                ~Paper.id.in_(extracted_ids)
            ).count()

            return status

    @classmethod
    def get_papers_needing_extraction(
        cls,
        limit: int = 20,
        prioritize_full_text: bool = True
    ) -> list[dict]:
        """Get papers that need extraction.

        Args:
            limit: Maximum papers to return
            prioritize_full_text: If True, papers with full text come first

        Returns:
            List of paper dicts
        """
        with get_session() as session:
            # Get IDs of papers that already have extractions
            extracted_ids = session.query(PaperContent.paper_id).subquery()

            query = session.query(Paper).filter(
                ~Paper.id.in_(extracted_ids),
                (Paper.full_text.isnot(None) & (Paper.full_text != '')) |
                (Paper.abstract.isnot(None) & (Paper.abstract != ''))
            )

            if prioritize_full_text:
                query = query.order_by(
                    Paper.full_text.is_(None).asc(),  # Full text first
                    Paper.date_added.desc()
                )
            else:
                query = query.order_by(Paper.date_added.desc())

            papers = query.limit(limit).all()

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "has_full_text": bool(p.full_text),
                    "has_abstract": bool(p.abstract),
                    "year": p.year,
                }
                for p in papers
            ]

    @classmethod
    def get_llm_status(cls) -> dict:
        """Get status of available LLM backends.

        Returns:
            Dict with availability status for each backend
        """
        ollama = OllamaClient()
        claude = ClaudeClient()

        return {
            "ollama": {
                "available": ollama.is_available(),
                "model": settings.ollama.reader_model,
                "host": settings.ollama.host,
            },
            "claude": {
                "available": claude.is_available(),
                "model": settings.claude.model,
                "api_key_configured": bool(settings.claude.api_key),
            },
            "recommended": "ollama" if ollama.is_available() else (
                "claude" if claude.is_available() else None
            )
        }

    @classmethod
    async def extract_paper(
        cls,
        paper_id: int,
        backend: Literal["ollama", "claude", "auto"] = "auto",
        force: bool = False
    ) -> PaperExtraction:
        """Extract structured content from a paper.

        Args:
            paper_id: Paper ID to extract
            backend: LLM backend to use (ollama, claude, or auto)
            force: If True, re-extract even if extraction exists

        Returns:
            PaperExtraction with results
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="Paper not found"
                )

            # Check if extraction exists
            if not force:
                existing = session.query(PaperContent).filter(
                    PaperContent.paper_id == paper_id
                ).first()
                if existing:
                    return PaperExtraction(
                        paper_id=paper_id,
                        paper_type=existing.paper_type,
                        topics=existing.topics,
                        one_sentence_summary=existing.one_sentence_summary,
                        key_findings=existing.key_findings,
                        methodology_summary=existing.methodology_summary,
                        extractor_model=existing.extractor_model,
                        success=True,
                        error="Already extracted (use force=true to re-extract)"
                    )

            # Check if paper has extractable content
            if not paper.abstract and not paper.full_text:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="Paper has no abstract or full text"
                )

            # Get LLM client
            client = cls._get_client(backend)
            if not client:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="No LLM backend available"
                )

            # Extract
            extraction = await client.extract(
                title=paper.title,
                abstract=paper.abstract or "",
                full_text=paper.full_text,
                paper_id=paper_id
            )

            # Store if successful
            if extraction.success:
                cls._store_extraction(session, paper_id, extraction)

            return extraction

    @classmethod
    def _get_client(cls, backend: str) -> Optional[LLMClient]:
        """Get an LLM client based on preference."""
        ollama = OllamaClient()
        claude = ClaudeClient()

        if backend == "ollama":
            return ollama if ollama.is_available() else None
        elif backend == "claude":
            return claude if claude.is_available() else None
        else:  # auto
            if ollama.is_available():
                return ollama
            elif claude.is_available():
                return claude
            return None

    @classmethod
    def _store_extraction(
        cls,
        session,
        paper_id: int,
        extraction: PaperExtraction
    ) -> None:
        """Store extraction in database."""
        content = session.query(PaperContent).filter(
            PaperContent.paper_id == paper_id
        ).first()

        if content:
            content.paper_type = extraction.paper_type
            content.topics = extraction.topics
            content.one_sentence_summary = extraction.one_sentence_summary
            content.key_findings = extraction.key_findings
            content.methodology_summary = extraction.methodology_summary
            content.extractor_model = extraction.extractor_model
            content.extraction_date = datetime.utcnow()
        else:
            content = PaperContent(
                paper_id=paper_id,
                paper_type=extraction.paper_type,
                topics=extraction.topics,
                one_sentence_summary=extraction.one_sentence_summary,
                key_findings=extraction.key_findings,
                methodology_summary=extraction.methodology_summary,
                extractor_model=extraction.extractor_model,
                extraction_depth="COMPREHENSIVE",
            )
            session.add(content)

        session.commit()
        logger.info(f"Stored extraction for paper {paper_id}")

    @classmethod
    async def extract_batch(
        cls,
        paper_ids: list[int] | None = None,
        limit: int = 10,
        backend: Literal["ollama", "claude", "auto"] = "auto",
        delay: float = 1.0
    ) -> ExtractionResult:
        """Extract multiple papers.

        Args:
            paper_ids: Specific papers to extract, or None to use queue
            limit: Maximum papers from queue if no IDs specified
            backend: LLM backend to use
            delay: Seconds between extractions (rate limiting)

        Returns:
            ExtractionResult with statistics
        """
        result = ExtractionResult()

        # Get papers to extract
        if paper_ids:
            papers = [{"id": pid} for pid in paper_ids]
        else:
            papers = cls.get_papers_needing_extraction(limit=limit)

        for paper_info in papers:
            try:
                extraction = await cls.extract_paper(
                    paper_id=paper_info["id"],
                    backend=backend
                )
                result.papers_processed += 1

                if extraction.success:
                    if "Already extracted" in (extraction.error or ""):
                        result.papers_skipped += 1
                    else:
                        result.papers_extracted += 1
                else:
                    result.papers_error += 1
                    if extraction.error:
                        result.errors.append(
                            f"Paper {paper_info['id']}: {extraction.error}"
                        )

                # Rate limiting
                if delay > 0:
                    await asyncio.sleep(delay)

            except Exception as e:
                result.papers_error += 1
                result.errors.append(f"Paper {paper_info['id']}: {str(e)}")
                logger.error(f"Batch extraction error: {e}")

        logger.info(
            f"Batch extraction complete: {result.papers_extracted} extracted, "
            f"{result.papers_skipped} skipped, {result.papers_error} errors"
        )

        return result

    @classmethod
    def delete_extraction(cls, paper_id: int) -> bool:
        """Delete extraction for a paper (for re-extraction).

        Args:
            paper_id: Paper ID

        Returns:
            True if deleted, False if not found
        """
        with get_session() as session:
            content = session.query(PaperContent).filter(
                PaperContent.paper_id == paper_id
            ).first()

            if content:
                session.delete(content)
                session.commit()
                logger.info(f"Deleted extraction for paper {paper_id}")
                return True

            return False
