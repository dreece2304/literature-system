"""
Extractor agent for AI-powered content extraction from papers.

Uses Claude API to extract structured data from papers and stores
results in literature-database.
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

import yaml
from loguru import logger

from config.settings import settings, PROJECT_ROOT
from src.services.claude_service import get_claude_service, ClaudeService
from src.services.database_client import get_database_client, DatabaseClient


@dataclass
class ExtractionResult:
    """Result of a paper extraction."""
    paper_id: int
    extraction_depth: str
    success: bool
    content: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: float = 0
    tokens_used: int = 0


@dataclass
class RelevanceResult:
    """Result of a relevance assessment."""
    paper_id: int
    project_name: str
    overall_relevance: str
    relevance_summary: str
    primary_use: Optional[str] = None
    success: bool = True
    error: Optional[str] = None


class ExtractorAgent:
    """
    AI-powered content extraction from papers.

    Extraction levels:
    - CITATION_ONLY: Basic metadata only (no AI)
    - BASIC: Summary, key findings, paper type
    - COMPREHENSIVE: Full structured data extraction

    Uses Claude API for high-quality extraction.
    """

    def __init__(
        self,
        claude_service: Optional[ClaudeService] = None,
        db_client: Optional[DatabaseClient] = None,
    ):
        """
        Initialize extractor agent.

        Args:
            claude_service: Claude API service (default: singleton)
            db_client: Database client (default: singleton)
        """
        self.claude = claude_service or get_claude_service()
        self.db = db_client or get_database_client()
        self.prompts = self._load_prompts()

        logger.info("ExtractorAgent initialized")

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
        """Get default prompts if file not found."""
        return {
            "system_prompt": """You are an expert scientific literature analyst specializing in materials science,
particularly thin film deposition, atomic layer deposition (ALD), and molecular layer deposition (MLD).

Your task is to extract structured information from academic papers with precision and accuracy.
Always respond with valid JSON matching the requested schema.""",

            "basic_extraction": {
                "template": """Analyze this paper and extract the following information:

PAPER METADATA:
Title: {title}
Authors: {authors}
Year: {year}
Abstract: {abstract}

FULL TEXT (if available):
{full_text}

Extract and return JSON with this structure:
{{
    "paper_type": "research_article|review|conference|book_chapter|thesis|preprint",
    "topics": ["list", "of", "relevant", "topics"],
    "one_sentence_summary": "What is the main contribution of this paper?",
    "key_findings": [
        {{
            "finding_id": "01",
            "statement": "Clear statement of the finding",
            "evidence": "How was this established?",
            "topics": ["relevant", "topics"]
        }}
    ],
    "methodology_summary": "Brief description of methods used"
}}

Guidelines:
- paper_type: Choose the most appropriate type
- topics: Select from common topics in the field (mld_growth, ald_growth, stability,
  spectroscopy, ftir, xps, mechanism, euv_lithography, resist_performance, etc.)
- key_findings: Extract 3-10 key findings with evidence
- Be precise and factual, only include information from the paper"""
            },

            "relevance_assessment": {
                "template": """Assess the relevance of this paper to the research project.

PAPER:
Title: {title}
Abstract: {abstract}
Key Findings: {key_findings}

PROJECT CONTEXT:
Project Name: {project_name}
Project Description: {project_context}

Evaluate and return JSON:
{{
    "overall_relevance": "CRITICAL|HIGH|MEDIUM|LOW|NONE",
    "relevance_summary": "2-3 sentence explanation of relevance",
    "primary_use": "introduction|methods|results|discussion|none"
}}

Guidelines:
- CRITICAL: Essential reference, directly addresses core research questions
- HIGH: Important supporting reference, provides key data or methods
- MEDIUM: Useful background or comparison
- LOW: Tangentially related
- NONE: Not relevant to this project"""
            }
        }

    async def extract_basic(self, paper_id: int) -> ExtractionResult:
        """
        Extract basic content from a paper.

        Args:
            paper_id: Paper ID to extract from

        Returns:
            ExtractionResult with extracted content
        """
        start_time = datetime.utcnow()

        try:
            # Get paper content
            paper = await self.db.get_paper_content_for_extraction(paper_id)
            if not paper:
                return ExtractionResult(
                    paper_id=paper_id,
                    extraction_depth="BASIC",
                    success=False,
                    error="Paper not found",
                )

            # Format prompt
            prompt_template = self.prompts.get("basic_extraction", {}).get(
                "template", self._get_default_prompts()["basic_extraction"]["template"]
            )

            prompt = prompt_template.format(
                title=paper.get("title", "Unknown"),
                authors=", ".join(paper.get("authors", [])),
                year=paper.get("year", "Unknown"),
                abstract=paper.get("abstract", "No abstract available"),
                full_text=paper.get("full_text", "")[:50000] if paper.get("full_text") else "Not available",
            )

            # Call Claude
            system = self.prompts.get("system_prompt", self._get_default_prompts()["system_prompt"])
            response = await self.claude.generate_json(
                prompt=prompt,
                system=system,
                temperature=0.1,
            )

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Prepare content for storage
            content = {
                "extraction_depth": "BASIC",
                "extractor_model": settings.claude.model,
                "paper_type": response.get("paper_type"),
                "topics": response.get("topics", []),
                "one_sentence_summary": response.get("one_sentence_summary"),
                "key_findings": response.get("key_findings", []),
                "methodology_summary": response.get("methodology_summary"),
            }

            # Store in database
            await self.db.store_extracted_content(paper_id, content)

            logger.info(f"Basic extraction complete for paper {paper_id}")

            return ExtractionResult(
                paper_id=paper_id,
                extraction_depth="BASIC",
                success=True,
                content=content,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Extraction failed for paper {paper_id}: {e}")
            return ExtractionResult(
                paper_id=paper_id,
                extraction_depth="BASIC",
                success=False,
                error=str(e),
                duration_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )

    async def extract_comprehensive(
        self,
        paper_id: int,
        domain_schema: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract comprehensive content including domain-specific data.

        Args:
            paper_id: Paper ID to extract from
            domain_schema: Optional domain schema (mld_growth, spectroscopy, mechanism)

        Returns:
            ExtractionResult with extracted content
        """
        # First do basic extraction
        basic_result = await self.extract_basic(paper_id)
        if not basic_result.success:
            return basic_result

        start_time = datetime.utcnow()

        try:
            # Get paper content
            paper = await self.db.get_paper_content_for_extraction(paper_id)

            # Determine domain schema from topics if not provided
            if not domain_schema and basic_result.content:
                topics = basic_result.content.get("topics", [])
                if "mld_growth" in topics or "ald_growth" in topics:
                    domain_schema = "mld_growth"
                elif "ftir" in topics or "xps" in topics or "spectroscopy" in topics:
                    domain_schema = "spectroscopy"
                elif "mechanism" in topics:
                    domain_schema = "mechanism"

            # If we have a domain schema, do additional extraction
            structured_data = {}
            if domain_schema:
                structured_data = await self._extract_domain_data(paper, domain_schema)

            # Update content with structured data
            content = basic_result.content.copy()
            content["extraction_depth"] = "COMPREHENSIVE"
            content["structured_data"] = structured_data

            # Store updated content
            await self.db.store_extracted_content(paper_id, content)

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ExtractionResult(
                paper_id=paper_id,
                extraction_depth="COMPREHENSIVE",
                success=True,
                content=content,
                duration_ms=duration_ms + basic_result.duration_ms,
            )

        except Exception as e:
            logger.error(f"Comprehensive extraction failed for paper {paper_id}: {e}")
            return ExtractionResult(
                paper_id=paper_id,
                extraction_depth="COMPREHENSIVE",
                success=False,
                error=str(e),
            )

    async def _extract_domain_data(
        self,
        paper: Dict[str, Any],
        domain_schema: str,
    ) -> Dict[str, Any]:
        """
        Extract domain-specific data.

        Args:
            paper: Paper data
            domain_schema: Domain schema name

        Returns:
            Extracted domain data
        """
        schema_prompts = {
            "mld_growth": """Extract MLD/ALD growth parameters from this paper:
- Materials: metal precursor, organic precursor, film type
- Deposition conditions: temperature, pressure, pulse times
- Growth rates: GPC values
- Film properties: thickness, density, refractive index

Return JSON:
{{
    "mld_growth": {{
        "materials": {{"metal_precursor": "", "organic_precursor": "", "film_type": ""}},
        "deposition_conditions": {{"temperature_C": null, "pressure_mTorr": null}},
        "growth_rates": [{{"GPC_nm": null, "measurement_method": ""}}],
        "film_properties": {{}}
    }}
}}""",

            "spectroscopy": """Extract spectroscopy data from this paper:
- FTIR peaks: wavenumber, assignment, intensity
- XPS binding energies: element, orbital, binding_energy_eV
- Other characterization: AFM, SEM, etc.

Return JSON:
{{
    "spectroscopy": {{
        "ftir_peaks": [{{"wavenumber_cm-1": null, "assignment": "", "intensity": ""}}],
        "xps_binding_energies": [{{"element": "", "orbital": "", "binding_energy_eV": null}}],
        "other_characterization": {{}}
    }}
}}""",

            "mechanism": """Extract reaction mechanism data from this paper:
- Reaction pathways
- Activation energies
- DFT calculations
- Rate constants

Return JSON:
{{
    "mechanism": {{
        "reactions": [{{"description": "", "equation": ""}}],
        "activation_energies": [{{"process": "", "Ea_eV": null}}],
        "dft_calculations": [{{"method": "", "result": ""}}]
    }}
}}"""
        }

        if domain_schema not in schema_prompts:
            return {}

        full_text = paper.get("full_text", "")[:30000] if paper.get("full_text") else ""
        prompt = f"""Paper: {paper.get('title', 'Unknown')}
Abstract: {paper.get('abstract', '')}

Text excerpt:
{full_text}

{schema_prompts[domain_schema]}

Only include data that is explicitly stated in the paper."""

        try:
            result = await self.claude.generate_json(
                prompt=prompt,
                system=self.prompts.get("system_prompt"),
                temperature=0.1,
            )
            return result
        except Exception as e:
            logger.warning(f"Domain extraction failed: {e}")
            return {}

    async def assess_relevance(
        self,
        paper_id: int,
        project_name: str,
        project_context: str,
    ) -> RelevanceResult:
        """
        Assess paper relevance to a research project.

        Args:
            paper_id: Paper ID
            project_name: Name of the project
            project_context: Description of the project's focus

        Returns:
            RelevanceResult with assessment
        """
        try:
            # Get paper data
            paper = await self.db.get_paper(paper_id)
            if not paper:
                return RelevanceResult(
                    paper_id=paper_id,
                    project_name=project_name,
                    overall_relevance="NONE",
                    relevance_summary="Paper not found",
                    success=False,
                    error="Paper not found",
                )

            # Get existing content if available
            content = await self.db.get_paper_extracted_content(paper_id)
            key_findings = json.dumps(content.get("key_findings", [])) if content else "Not extracted"

            # Format prompt
            prompt_template = self.prompts.get("relevance_assessment", {}).get(
                "template", self._get_default_prompts()["relevance_assessment"]["template"]
            )

            prompt = prompt_template.format(
                title=paper.get("title", "Unknown"),
                abstract=paper.get("abstract", "No abstract"),
                key_findings=key_findings,
                project_name=project_name,
                project_context=project_context,
            )

            # Call Claude
            response = await self.claude.generate_json(
                prompt=prompt,
                system=self.prompts.get("system_prompt"),
                temperature=0.1,
            )

            # Store relevance
            await self.db.store_relevance(
                paper_id=paper_id,
                project_name=project_name,
                overall_relevance=response.get("overall_relevance", "MEDIUM"),
                relevance_summary=response.get("relevance_summary", ""),
                primary_use=response.get("primary_use"),
            )

            return RelevanceResult(
                paper_id=paper_id,
                project_name=project_name,
                overall_relevance=response.get("overall_relevance", "MEDIUM"),
                relevance_summary=response.get("relevance_summary", ""),
                primary_use=response.get("primary_use"),
            )

        except Exception as e:
            logger.error(f"Relevance assessment failed for paper {paper_id}: {e}")
            return RelevanceResult(
                paper_id=paper_id,
                project_name=project_name,
                overall_relevance="NONE",
                relevance_summary="Assessment failed",
                success=False,
                error=str(e),
            )

    async def batch_extract(
        self,
        paper_ids: List[int],
        level: str = "BASIC",
    ) -> List[ExtractionResult]:
        """
        Extract content from multiple papers.

        Args:
            paper_ids: List of paper IDs
            level: Extraction level (BASIC or COMPREHENSIVE)

        Returns:
            List of ExtractionResults
        """
        results = []

        for i, paper_id in enumerate(paper_ids):
            logger.info(f"Extracting paper {i+1}/{len(paper_ids)}: {paper_id}")

            if level == "COMPREHENSIVE":
                result = await self.extract_comprehensive(paper_id)
            else:
                result = await self.extract_basic(paper_id)

            results.append(result)

            # Log progress
            success_count = sum(1 for r in results if r.success)
            logger.info(f"Progress: {i+1}/{len(paper_ids)} ({success_count} successful)")

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
            "agent_name": "extractor",
            "agent_type": "ExtractorAgent",
            "model": settings.claude.model,
            "prompts_loaded": len(self.prompts),
        }
