"""
Local extractor agent for AI-powered content extraction using Ollama.

Uses local Qwen models via Ollama for cost-effective batch extraction.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

import yaml
from loguru import logger

from config.settings import PROJECT_ROOT
from src.services.llm_service import LLMService
from src.services.database_client import get_database_client, DatabaseClient


@dataclass
class LocalExtractionResult:
    """Result of a local paper extraction."""
    paper_id: int
    extraction_depth: str
    success: bool
    content: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0
    model: str = ""


class LocalExtractorAgent:
    """
    AI-powered content extraction using local Ollama models.

    Uses Qwen for cost-effective batch extraction.
    Suitable for extracting from papers that don't need Claude's quality.
    """

    # Use smaller model for basic extraction
    DEFAULT_MODEL = "qwen2.5:14b"

    def __init__(
        self,
        db_client: Optional[DatabaseClient] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize local extractor agent.

        Args:
            db_client: Database client (default: singleton)
            model: Ollama model to use (default: qwen2.5:14b)
        """
        self.db = db_client or get_database_client()
        self.model = model or self.DEFAULT_MODEL
        self.llm = LLMService()
        self.prompts = self._load_prompts()

        logger.info(f"LocalExtractorAgent initialized with model {self.model}")

    def _load_prompts(self) -> Dict[str, Any]:
        """Load extraction prompts from YAML."""
        prompt_file = PROJECT_ROOT / "config" / "prompts" / "extractor.yaml"

        if not prompt_file.exists():
            logger.warning(f"Prompt file not found: {prompt_file}")
            return self._get_default_prompts()

        try:
            with open(prompt_file, "r") as f:
                prompts = yaml.safe_load(f)
                logger.debug(f"Loaded prompts from {prompt_file}")
                return prompts
        except Exception as e:
            logger.error(f"Failed to load prompts: {e}")
            return self._get_default_prompts()

    def _get_default_prompts(self) -> Dict[str, Any]:
        """Get default prompts for extraction."""
        return {
            "system_prompt": """You are an expert scientific literature analyst specializing in materials science,
particularly thin film deposition, atomic layer deposition (ALD), and molecular layer deposition (MLD).

Your task is to extract structured information from academic papers with precision and accuracy.
Always respond with valid JSON matching the requested schema. Do not include any text outside the JSON.""",

            "basic_extraction": {
                "template": """Analyze this paper and extract structured information.

PAPER:
Title: {title}
Authors: {authors}
Year: {year}
Abstract: {abstract}

Return ONLY valid JSON with this exact structure:
{{
    "paper_type": "research_article",
    "topics": ["topic1", "topic2"],
    "one_sentence_summary": "Main contribution of this paper",
    "key_findings": [
        {{
            "finding_id": "01",
            "statement": "Finding statement",
            "evidence": "How established",
            "topics": ["topic"]
        }}
    ],
    "methodology_summary": "Brief methods description"
}}

Guidelines:
- paper_type: research_article, review, conference, book_chapter, thesis, or preprint
- topics: mld_growth, ald_growth, stability, spectroscopy, ftir, xps, mechanism,
  euv_lithography, resist_performance, alucone, zincone, etc.
- key_findings: 3-7 findings with evidence
- Be factual and precise"""
            },

            "relevance_assessment": {
                "template": """Assess relevance of this paper to the research project.

PAPER:
Title: {title}
Abstract: {abstract}

PROJECT: {project_name}
{project_context}

Return ONLY valid JSON:
{{
    "overall_relevance": "HIGH",
    "relevance_summary": "2-3 sentence explanation",
    "primary_use": "methods"
}}

Relevance levels:
- CRITICAL: Essential, directly addresses core questions
- HIGH: Important supporting reference
- MEDIUM: Useful background
- LOW: Tangentially related
- NONE: Not relevant

Primary use: introduction, methods, results, discussion, or none"""
            }
        }

    async def extract_basic(self, paper_id: int) -> LocalExtractionResult:
        """
        Extract basic content from a paper using local model.

        Args:
            paper_id: Paper ID to extract from

        Returns:
            LocalExtractionResult with extracted content
        """
        start_time = datetime.utcnow()

        try:
            # Get paper content
            paper = await self.db.get_paper_content_for_extraction(paper_id)
            if not paper:
                return LocalExtractionResult(
                    paper_id=paper_id,
                    extraction_depth="BASIC",
                    success=False,
                    error="Paper not found",
                    model=self.model,
                )

            # Format prompt
            prompt_template = self.prompts.get("basic_extraction", {}).get(
                "template", self._get_default_prompts()["basic_extraction"]["template"]
            )

            # Truncate abstract if too long
            abstract = paper.get("abstract", "No abstract available")
            if len(abstract) > 2000:
                abstract = abstract[:2000] + "..."

            prompt = prompt_template.format(
                title=paper.get("title", "Unknown"),
                authors=", ".join(paper.get("authors", [])[:5]),  # Limit authors
                year=paper.get("year", "Unknown"),
                abstract=abstract,
            )

            # Call local LLM
            system = self.prompts.get("system_prompt", self._get_default_prompts()["system_prompt"])

            response = await self.llm.generate_json(
                prompt=prompt,
                system=system,
                model=self.model,
                temperature=0.1,
            )

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            if not response:
                return LocalExtractionResult(
                    paper_id=paper_id,
                    extraction_depth="BASIC",
                    success=False,
                    error="Empty response from model",
                    duration_ms=duration_ms,
                    model=self.model,
                )

            # Prepare content for storage
            content = {
                "extraction_depth": "BASIC",
                "extractor_model": self.model,
                "paper_type": response.get("paper_type", "research_article"),
                "topics": response.get("topics", []),
                "one_sentence_summary": response.get("one_sentence_summary"),
                "key_findings": response.get("key_findings", []),
                "methodology_summary": response.get("methodology_summary"),
            }

            # Store in database
            await self.db.store_extracted_content(paper_id, content)

            logger.info(f"Local extraction complete for paper {paper_id}")

            return LocalExtractionResult(
                paper_id=paper_id,
                extraction_depth="BASIC",
                success=True,
                content=content,
                duration_ms=duration_ms,
                model=self.model,
            )

        except Exception as e:
            logger.error(f"Local extraction failed for paper {paper_id}: {e}")
            return LocalExtractionResult(
                paper_id=paper_id,
                extraction_depth="BASIC",
                success=False,
                error=str(e),
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
                model=self.model,
            )

    async def assess_relevance(
        self,
        paper_id: int,
        project_name: str,
        project_context: str,
    ) -> Dict[str, Any]:
        """
        Assess paper relevance to a research project using local model.

        Args:
            paper_id: Paper ID
            project_name: Name of the project
            project_context: Description of the project's focus

        Returns:
            Dict with relevance assessment
        """
        try:
            # Get paper data
            paper = await self.db.get_paper(paper_id)
            if not paper:
                return {
                    "paper_id": paper_id,
                    "project_name": project_name,
                    "overall_relevance": "NONE",
                    "relevance_summary": "Paper not found",
                    "success": False,
                }

            # Format prompt
            prompt_template = self.prompts.get("relevance_assessment", {}).get(
                "template", self._get_default_prompts()["relevance_assessment"]["template"]
            )

            prompt = prompt_template.format(
                title=paper.get("title", "Unknown"),
                abstract=paper.get("abstract", "No abstract")[:1500],
                project_name=project_name,
                project_context=project_context,
            )

            # Call local LLM
            response = await self.llm.generate_json(
                prompt=prompt,
                system=self.prompts.get("system_prompt"),
                model=self.model,
                temperature=0.1,
            )

            if not response:
                return {
                    "paper_id": paper_id,
                    "project_name": project_name,
                    "overall_relevance": "NONE",
                    "relevance_summary": "Failed to get response",
                    "success": False,
                }

            # Store relevance
            await self.db.store_relevance(
                paper_id=paper_id,
                project_name=project_name,
                overall_relevance=response.get("overall_relevance", "MEDIUM"),
                relevance_summary=response.get("relevance_summary", ""),
                primary_use=response.get("primary_use"),
            )

            return {
                "paper_id": paper_id,
                "project_name": project_name,
                "overall_relevance": response.get("overall_relevance", "MEDIUM"),
                "relevance_summary": response.get("relevance_summary", ""),
                "primary_use": response.get("primary_use"),
                "success": True,
            }

        except Exception as e:
            logger.error(f"Local relevance assessment failed for paper {paper_id}: {e}")
            return {
                "paper_id": paper_id,
                "project_name": project_name,
                "overall_relevance": "NONE",
                "relevance_summary": f"Assessment failed: {e}",
                "success": False,
            }

    async def batch_extract(
        self,
        paper_ids: List[int],
        progress_callback: Optional[callable] = None,
    ) -> List[LocalExtractionResult]:
        """
        Extract content from multiple papers using local model.

        Args:
            paper_ids: List of paper IDs
            progress_callback: Optional callback(current, total, result)

        Returns:
            List of LocalExtractionResults
        """
        results = []
        total = len(paper_ids)

        for i, paper_id in enumerate(paper_ids):
            logger.info(f"Extracting paper {i+1}/{total}: {paper_id}")

            result = await self.extract_basic(paper_id)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total, result)

            # Log progress
            success_count = sum(1 for r in results if r.success)
            logger.info(f"Progress: {i+1}/{total} ({success_count} successful)")

        return results

    async def get_extraction_queue(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get papers that need extraction.

        Args:
            limit: Maximum papers to return

        Returns:
            List of papers needing extraction
        """
        queue = await self.db.get_extraction_queue(limit=limit)
        return queue.get("papers_needing_extraction", [])

    def get_info(self) -> Dict[str, Any]:
        """Get agent information."""
        return {
            "agent_name": "local_extractor",
            "agent_type": "LocalExtractorAgent",
            "model": self.model,
            "prompts_loaded": len(self.prompts),
        }
