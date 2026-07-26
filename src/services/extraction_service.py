"""Extraction Service - Unified PDF processing and AI-powered paper analysis.

Consolidates:
- PDF text extraction and chunking (from ChunkedExtractionService)
- Queue management for extraction (from ChunkingQueueService)
- AI-powered content extraction (Ollama/Claude)

Architecture:
    ExtractionService -> PDF Processing -> PaperChunk, PaperTable, etc.
                      -> LLMClient (Ollama/Claude) -> AI extraction
                      -> PaperService -> Database
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal, Callable, Any
from abc import ABC, abstractmethod

# Progress callback type: (pass_num, current, total, message)
ProgressCallback = Callable[[int, int, int, str], Any]

import httpx
import pdfplumber

from literature_core import (
    get_session, get_logger, Paper, PaperContent, PaperChunk,
    PaperTable, PaperFigure, PaperReference, ExtractionMetadata,
    ChunkingStatus, EnrichmentStatus,
)
from sqlalchemy import func
from config.ai_settings import settings
from .paper_service import PaperService
from .extraction_prompts import (
    get_extraction_prompt,
    get_chunk_extraction_prompt,
    get_consolidation_prompt,
    parse_extraction_response,
    validate_extraction,
)

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Target chunk size in words (roughly ~4000 tokens)
DEFAULT_CHUNK_SIZE = 2000

# Progress callback type: (phase, detail, progress_pct) -> None
# phase: "text", "ocr", "tables", "figures", "references", "chunking"
# detail: human-readable status like "Page 3/10"
# progress_pct: 0-100 or None if indeterminate
ProgressCallback = Callable[[str, str, Optional[int]], None]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PDFExtractionResult:
    """Result of PDF extraction (text, tables, figures, references)."""
    success: bool
    paper_id: int
    chunk_count: int = 0
    table_count: int = 0
    figure_count: int = 0
    reference_count: int = 0
    word_count: int = 0
    page_count: int = 0
    error: str | None = None


@dataclass
class ChunkingResult:
    """Result of chunking operation."""
    paper_id: int
    status: str  # complete, failed, skipped
    chunk_count: int = 0
    error: str | None = None


@dataclass
class QueueStats:
    """Queue statistics."""
    pending: int
    processing: int
    complete: int
    failed: int
    none: int
    total_with_pdf: int


@dataclass
class SectionHint:
    """A detected section from heuristic scanning."""
    name: str                    # Detected section name (e.g., "Introduction", "Methods")
    start_position: int          # Character position in text
    confidence: float            # 0.0-1.0 confidence level
    matched_pattern: str         # What pattern matched (for debugging)


@dataclass
class DocumentStructure:
    """Heuristic document structure hints (may be inaccurate).

    This is the result of quick regex-based section detection.
    The LLM should validate/correct this during extraction.
    """
    sections: list[SectionHint] = field(default_factory=list)
    detected_type: str = "unknown"  # research_article, review, conference, etc.
    type_confidence: float = 0.0
    has_abstract: bool = False
    has_references: bool = False
    estimated_word_count: int = 0

    def to_prompt_hint(self) -> str:
        """Format for including in LLM prompt as hints."""
        if not self.sections:
            return "No clear section structure detected."

        lines = [f"Detected document type: {self.detected_type} (confidence: {self.type_confidence:.0%})"]
        lines.append("Detected sections (may be inaccurate):")
        for s in self.sections:
            conf = "high" if s.confidence > 0.8 else "medium" if s.confidence > 0.5 else "low"
            lines.append(f"  - {s.name} ({conf} confidence)")
        return "\n".join(lines)


@dataclass
class ChunkProcessingState:
    """State tracking for multi-chunk extraction.

    Passed between chunk extractions to maintain context.
    Can be saved/loaded for crash recovery.
    """
    paper_id: int
    chunks_processed: int = 0
    current_section: str = "unknown"
    section_in_progress: bool = False
    sections_seen: list[str] = field(default_factory=list)
    structure_corrections: list[str] = field(default_factory=list)
    document_type: str = "unknown"
    type_confidence: float = 0.0

    # Accumulated extractions from chunks
    key_findings: list[str] = field(default_factory=list)
    quantitative_results: list[dict] = field(default_factory=list)
    cited_claims: list[dict] = field(default_factory=list)

    # Facts-only forward context carried between chunks (never findings/summaries)
    glossary: dict[str, str] = field(default_factory=dict)

    def update_from_chunk(self, chunk_result: dict) -> None:
        """Accumulate FACTS only (sections, glossary) - never findings/summaries."""
        self.chunks_processed += 1
        for section in chunk_result.get("sections_in_chunk", []) or []:
            if section not in self.sections_seen:
                self.sections_seen.append(section)
            self.current_section = section
        terms = chunk_result.get("defined_terms") or {}
        if isinstance(terms, dict):
            self.glossary.update({str(k): str(v) for k, v in terms.items()})

    def save_checkpoint(self) -> None:
        """Save state to database for crash recovery."""
        from literature_core import get_session
        from literature_core.models import ExtractionMetadata
        with get_session() as session:
            meta = session.query(ExtractionMetadata).filter_by(paper_id=self.paper_id).first()
            if meta:
                meta.extraction_checkpoint = {
                    "chunks_processed": self.chunks_processed,
                    "sections_seen": self.sections_seen,
                    "glossary": self.glossary,
                    "current_section": self.current_section,
                }
                session.commit()

    @classmethod
    def load_checkpoint(cls, paper_id: int) -> Optional["ChunkProcessingState"]:
        """Load state from database for crash recovery."""
        from literature_core import get_session
        from literature_core.models import ExtractionMetadata
        with get_session() as session:
            meta = session.query(ExtractionMetadata).filter_by(paper_id=paper_id).first()
            if not meta or not meta.extraction_checkpoint:
                return None
            cp = meta.extraction_checkpoint
            return cls(
                paper_id=paper_id,
                chunks_processed=cp.get("chunks_processed", 0),
                sections_seen=cp.get("sections_seen", []),
                glossary=cp.get("glossary", {}),
                current_section=cp.get("current_section", "unknown"),
            )

    def to_prompt_context(self) -> str:
        """Format accumulated state for next chunk's prompt."""
        lines = []
        if self.chunks_processed > 0:
            lines.append(f"Chunks processed so far: {self.chunks_processed}")
            lines.append(f"Previous chunk ended in section: {self.current_section}")
            if self.sections_seen:
                lines.append(f"Sections seen so far: {', '.join(self.sections_seen)}")
            if self.document_type != "unknown":
                lines.append(f"Document type (from earlier chunks): {self.document_type}")
        if self.glossary:
            terms = "; ".join(f"{k} = {v}" for k, v in sorted(self.glossary.items()))
            lines.append(f"Terms defined earlier in this paper: {terms}")
        return "\n".join(lines) if lines else ""


@dataclass
class QualityReport:
    """Quality assessment for a paper's extraction."""
    paper_id: int
    paper_title: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 1.0  # 0.0-1.0, 1.0 = no issues

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def needs_review(self) -> bool:
        return self.score < 0.7


# =============================================================================
# AI Extraction Data Classes
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
    # Extended extraction fields
    research_context: Optional[dict] = None  # problem_addressed, novelty, limitations
    discussion_summary: Optional[str] = None  # Key interpretations and discussion points
    future_directions: Optional[list[str]] = None  # Suggested future work
    # New citation-matching fields
    quantitative_results: Optional[list[dict]] = None  # metric, value, unit, conditions
    citable_claims: Optional[list[str]] = None  # Specific quotable assertions
    techniques_used: Optional[list[dict]] = None  # technique, purpose, specifics
    experimental_conditions: Optional[dict] = None  # materials, temp, pressure, params
    prior_work_comparison: Optional[list[dict]] = None  # reference_claim, this_work, improvement
    citation_contexts: Optional[dict] = None  # intro, methods, results, discussion
    # DEPRECATED: cited_references removed from extraction prompt due to hallucination issues.
    # LLM cannot reliably map claims to reference numbers without the actual reference list.
    # Kept for backwards compatibility with existing extractions.
    cited_references: Optional[list[dict]] = None  # DEPRECATED - do not use
    # Chunk extractions for claim citation processing
    chunk_extractions: Optional[list[dict]] = None  # Raw chunk extraction data
    # Verbose output for debugging
    raw_response: Optional[str] = None
    prompt_used: Optional[str] = None
    elapsed_seconds: Optional[float] = None


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
        full_text: Optional[str] = None,
        paper_id: int = 0,
        verbose: bool = False
    ) -> PaperExtraction:
        """Extract structured content from a paper.

        Args:
            title: Paper title
            abstract: Paper abstract
            full_text: Optional full text content
            paper_id: Paper ID for the result
            verbose: If True, include raw_response and prompt_used in result
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM is available."""
        pass


class OllamaClient(LLMClient):
    """Ollama client for local LLM inference."""

    # Context limits based on paper size
    # qwen2.5 supports 128K tokens ≈ 512K chars
    # But processing time scales with input size:
    # - 20K chars (~5K tokens): ~60s
    # - 50K chars (~12K tokens): ~120s
    # - 100K chars (~25K tokens): ~300s
    #
    # Balance speed vs coverage (timeout is 300s):
    # - Under 50K: use full text (fits in timeout)
    # - 50K-150K: smart extraction to 60K limit
    # - Over 150K: aggressive extraction to 80K limit
    FULL_TEXT_THRESHOLD = 50000   # Papers under this use full text
    MAX_FULL_TEXT_CHARS = 60000   # For medium papers (50K-150K)
    MAX_LONG_PAPER_CHARS = 80000  # For very long papers (>150K)

    @staticmethod
    def _extract_key_sections(
        full_text: str,
        max_chars: int = 50000,
        prioritize_sections: bool = True
    ) -> str:
        """Extract key sections from full text for better summarization.

        Strategy varies by paper length:
        - Short papers (<40K): Use full text
        - Medium papers (40K-100K): Smart extraction with section detection
        - Long papers (>100K): Aggressive section extraction with more context

        Args:
            full_text: Complete paper text
            max_chars: Maximum characters to return
            prioritize_sections: If True, find and prioritize key sections

        Returns:
            Extracted text with key sections
        """
        import re

        text_len = len(full_text)

        # Short papers: use everything
        if text_len <= max_chars:
            return full_text

        # Section markers (case-insensitive patterns) - ordered by importance
        section_patterns = [
            # Results sections (highest priority)
            (r'\n\s*(?:\d\.?\s*)?results?\s*\n', 5000),
            (r'\n\s*(?:\d\.?\s*)?results?\s+and\s+discussion\s*\n', 6000),
            # Discussion sections
            (r'\n\s*(?:\d\.?\s*)?discussion\s*\n', 5000),
            # Conclusion sections
            (r'\n\s*(?:\d\.?\s*)?conclusion[s]?\s*\n', 4000),
            (r'\n\s*(?:\d\.?\s*)?summary\s*\n', 3000),
            # Methods (for experimental details)
            (r'\n\s*(?:\d\.?\s*)?(?:materials?\s+and\s+)?methods?\s*\n', 3000),
            (r'\n\s*(?:\d\.?\s*)?experimental\s*\n', 3000),
        ]

        # Calculate section sizes based on paper length
        # Longer papers get proportionally more from each section
        if text_len > 150000:
            # Very long papers (>150K): aggressive extraction
            intro_chars = min(6000, max_chars // 5)
            end_chars = min(4000, max_chars // 6)
        elif text_len > 100000:
            # Long papers (100K-150K)
            intro_chars = min(5000, max_chars // 4)
            end_chars = min(4000, max_chars // 5)
        else:
            # Medium papers (40K-100K)
            intro_chars = min(6000, max_chars // 3)
            end_chars = min(5000, max_chars // 4)

        # Always include beginning (abstract, intro)
        intro = full_text[:intro_chars]

        # Always include end (conclusion area)
        conclusion = full_text[-end_chars:]

        # Budget for middle sections
        remaining_budget = max_chars - len(intro) - end_chars
        middle_sections = []
        used_ranges = set()  # Track what we've already included

        if prioritize_sections:
            for pattern, section_chars in section_patterns:
                if remaining_budget <= 0:
                    break

                matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
                for match in matches:
                    start = match.start()
                    # Don't include if overlaps with intro or conclusion
                    if start < intro_chars or start > (text_len - end_chars - section_chars):
                        continue

                    # Check for overlap with already extracted sections
                    overlaps = any(
                        abs(start - used_start) < section_chars
                        for used_start in used_ranges
                    )
                    if overlaps:
                        continue

                    # Extract section
                    chars_to_take = min(section_chars, remaining_budget)
                    section_text = full_text[start:start + chars_to_take]
                    middle_sections.append((start, section_text))
                    used_ranges.add(start)
                    remaining_budget -= len(section_text)

        # Sort sections by position in document
        middle_sections.sort(key=lambda x: x[0])

        # Calculate how much content we have so far
        section_content_size = sum(len(s[1]) for s in middle_sections)
        current_size = len(intro) + section_content_size + end_chars + 100  # 100 for markers

        # Build result
        if middle_sections and current_size >= max_chars * 0.5:
            # Found enough sections to meet at least 50% of budget
            parts = [intro]
            for _, section_text in middle_sections:
                parts.append("\n\n[...section boundary...]\n\n")
                parts.append(section_text)
            parts.append("\n\n[...section boundary...]\n\n")
            parts.append(conclusion)
            result = "".join(parts)
        else:
            # Not enough sections found - use even sampling to fill budget
            # This ensures we use the full max_chars limit
            result = OllamaClient._sample_evenly(full_text, intro_chars, end_chars, max_chars)

        return result[:max_chars]

    @staticmethod
    def _sample_evenly(
        full_text: str,
        intro_chars: int,
        end_chars: int,
        max_chars: int
    ) -> str:
        """Sample text evenly when section detection fails.

        Takes samples from multiple positions to cover the document broadly.
        """
        text_len = len(full_text)
        intro = full_text[:intro_chars]
        conclusion = full_text[-end_chars:]

        # Calculate how much we can take from middle sections
        marker_overhead = 100  # For [...] markers
        remaining = max_chars - intro_chars - end_chars - marker_overhead

        # Divide into 3 chunks from different parts of the paper
        chunk_size = remaining // 3

        # Sample from 25%, 50%, and 75% of the document
        positions = [
            int(text_len * 0.25),
            int(text_len * 0.50),
            int(text_len * 0.70),
        ]

        chunks = []
        for pos in positions:
            # Ensure we don't overlap with intro or conclusion
            if pos < intro_chars:
                pos = intro_chars + 100
            if pos + chunk_size > text_len - end_chars:
                pos = text_len - end_chars - chunk_size - 100
            chunks.append(full_text[pos:pos + chunk_size])

        return (
            intro +
            "\n\n[...]\n\n" + chunks[0] +
            "\n\n[...]\n\n" + chunks[1] +
            "\n\n[...]\n\n" + chunks[2] +
            "\n\n[...]\n\n" + conclusion
        )

    # Legacy prompt kept for backward compatibility - use extraction_prompts.py for new extractions
    _LEGACY_EXTRACTION_PROMPT = """You are an expert research paper analyst specializing in scientific literature extraction for citation matching.

Analyze this paper carefully and extract structured information optimized for finding relevant citations.

PAPER TITLE: {title}

ABSTRACT: {abstract}

{full_text_section}

Extract the following in JSON format. Be thorough and specific - this data will be used to match papers to citation needs:

{{
    "paper_type": "research_article|review|conference|preprint|thesis|book_chapter|patent|other",

    "topics": [
        "Primary research field",
        "Secondary topic/subfield",
        "Key technique or method",
        "Application domain",
        "Related concept"
    ],

    "one_sentence_summary": "A comprehensive sentence capturing: WHAT was done, HOW it was done, and WHAT was the main result/contribution",

    "key_findings": [
        "Primary quantitative result with specific numbers (e.g., 'achieved 95% efficiency at 300K')",
        "Secondary finding with supporting data",
        "Third significant result or observation",
        "Unexpected or notable discovery",
        "Performance comparison to prior work (if available)"
    ],

    "quantitative_results": [
        {{"metric": "growth rate", "value": "1.1", "unit": "Å/cycle", "conditions": "at 150-300°C"}},
        {{"metric": "efficiency", "value": "95", "unit": "%", "conditions": "room temperature"}},
        {{"metric": "resolution", "value": "10", "unit": "nm", "conditions": "using EUV"}}
    ],

    "citable_claims": [
        "Specific, quotable assertion that could be cited (e.g., 'ALD enables atomic-level thickness control')",
        "Another concrete claim with evidence from this paper",
        "Third major assertion or conclusion"
    ],

    "techniques_used": [
        {{"technique": "atomic layer deposition", "purpose": "thin film growth", "specifics": "TMA/H2O at 200°C"}},
        {{"technique": "XPS", "purpose": "surface composition analysis", "specifics": "Al 2p peak analysis"}}
    ],

    "experimental_conditions": {{
        "materials": ["Al2O3", "TiO2", "Si substrate"],
        "temperature_range": "150-400°C",
        "pressure": "1-10 Torr",
        "key_parameters": ["growth rate", "film thickness", "precursor pulse time"]
    }},

    "methodology_summary": "Detailed description covering: (1) experimental/computational setup, (2) key parameters and conditions, (3) measurement techniques used, (4) data analysis methods. 4-6 sentences.",

    "discussion_summary": "Summary of the authors' interpretation of results: What do the findings mean? How do they compare to expectations or prior work? What mechanisms or explanations are proposed? 3-5 sentences.",

    "prior_work_comparison": [
        {{"reference_claim": "previous work achieved X", "this_work": "we improved to Y", "improvement": "2x better"}},
        {{"reference_claim": "conventional method has limitation", "this_work": "our approach overcomes it", "improvement": "first demonstration"}}
    ],

    "research_context": {{
        "problem_addressed": "What specific scientific/engineering problem or knowledge gap motivated this work?",
        "novelty": "What is new or different about this approach? What hadn't been done before?",
        "limitations": "What limitations, caveats, or boundary conditions do the authors acknowledge?",
        "significance": "Why does this matter? What is the broader impact or application potential?"
    }},

    "citation_contexts": {{
        "introduction": "Why cite in intro? (e.g., 'foundational work on ALD mechanism')",
        "methods": "Why cite in methods? (e.g., 'standard ALD recipe for Al2O3')",
        "results": "Why cite for comparison? (e.g., 'benchmark growth rate data')",
        "discussion": "Why cite in discussion? (e.g., 'proposed surface reaction mechanism')"
    }},

    "future_directions": [
        "First suggested direction for future research",
        "Second area for follow-up investigation",
        "Open question remaining from this work"
    ]
}}

GUIDELINES:
- Include specific numbers, percentages, temperatures, dimensions where available
- Use established scientific terminology for topics
- Key findings and citable_claims should be concrete assertions with evidence, not vague statements
- quantitative_results should extract ALL numerical results with proper units and conditions
- techniques_used should list specific characterization and fabrication methods
- prior_work_comparison captures how this work advances the field
- citation_contexts explains WHY someone might cite this paper in different manuscript sections
- If information is genuinely not available, use null or empty array (don't fabricate)
- For methodology, be specific about techniques (e.g., "FTIR spectroscopy" not "spectroscopy")

Respond ONLY with valid JSON, no markdown formatting or explanation."""

    def __init__(self):
        self.host = settings.ollama.host
        self.model = settings.ollama.reader_model
        self.quick_model = settings.ollama.quick_extractor_model
        self.deep_model = settings.ollama.deep_extractor_model
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
        paper_id: int = 0,
        verbose: bool = False
    ) -> PaperExtraction:
        """Extract structured content using Ollama.

        Args:
            title: Paper title
            abstract: Paper abstract
            full_text: Optional full text content
            paper_id: Paper ID for the result
            verbose: If True, include raw_response and prompt_used in result
        """
        import time
        start_time = time.time()

        # Prepare prompt with adaptive text extraction based on paper length
        full_text_section = ""
        if full_text:
            total_chars = len(full_text)

            # Choose strategy based on paper length
            # Thresholds: 50K (full), 50K-150K (smart), >150K (aggressive)
            if total_chars <= self.FULL_TEXT_THRESHOLD:
                # Short papers (<50K): use full text
                extracted = full_text
                strategy = "full"
            elif total_chars <= 150000:
                # Medium papers (50K-150K): smart extraction to 60K
                extracted = self._extract_key_sections(full_text, self.MAX_FULL_TEXT_CHARS)
                strategy = "smart"
            else:
                # Long papers (>150K): aggressive extraction to 80K
                extracted = self._extract_key_sections(full_text, self.MAX_LONG_PAPER_CHARS)
                strategy = "aggressive"

            chars_used = len(extracted)
            coverage = (chars_used / total_chars * 100) if total_chars > 0 else 100
            full_text_section = f"FULL TEXT ({chars_used:,} of {total_chars:,} chars, {coverage:.0f}% - {strategy}):\n{extracted}\n"

        prompt = self._LEGACY_EXTRACTION_PROMPT.format(
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
                            "num_predict": 2048,  # Tokens for response
                            "num_ctx": 8192,  # Reduced from 32K for speed
                        }
                    }
                )

                elapsed = time.time() - start_time

                if response.status_code != 200:
                    return PaperExtraction(
                        paper_id=paper_id,
                        success=False,
                        error=f"Ollama error: {response.status_code}",
                        elapsed_seconds=elapsed,
                        prompt_used=prompt if verbose else None
                    )

                data = response.json()
                response_text = data.get("response", "")

                # Parse JSON from response
                extraction = self._parse_extraction(response_text, paper_id)
                extraction.extractor_model = f"ollama/{self.model}"
                extraction.elapsed_seconds = elapsed

                # Add verbose output
                if verbose:
                    extraction.raw_response = response_text
                    extraction.prompt_used = prompt

                return extraction

        except httpx.TimeoutException:
            elapsed = time.time() - start_time
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error="Ollama timeout",
                elapsed_seconds=elapsed,
                prompt_used=prompt if verbose else None
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=str(e),
                elapsed_seconds=elapsed,
                prompt_used=prompt if verbose else None
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
                research_context=data.get("research_context"),
                discussion_summary=data.get("discussion_summary"),
                future_directions=data.get("future_directions", []),
                # New citation-matching fields
                quantitative_results=data.get("quantitative_results", []),
                citable_claims=data.get("citable_claims", []),
                techniques_used=data.get("techniques_used", []),
                experimental_conditions=data.get("experimental_conditions"),
                prior_work_comparison=data.get("prior_work_comparison", []),
                citation_contexts=data.get("citation_contexts"),
                cited_references=data.get("cited_references", []),
                success=True
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction JSON: {e}")
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=f"JSON parse error: {e}"
            )

    async def extract_quick(
        self,
        title: str,
        abstract: str,
        journal: Optional[str] = None,
        paper_id: int = 0,
        verbose: bool = False
    ) -> PaperExtraction:
        """Extract quick tier (abstract-only) using unified prompts.

        Args:
            title: Paper title
            abstract: Paper abstract
            journal: Journal name (helps with paper_type inference)
            paper_id: Paper ID for the result
            verbose: If True, include raw_response and prompt_used in result

        Returns:
            PaperExtraction with paper_type, topics, one_sentence_summary
        """
        import time
        start_time = time.time()

        # Generate prompt using unified prompts module
        prompt = get_extraction_prompt(
            title=title,
            abstract=abstract or "",
            tier="quick",
            journal=journal,
        )

        try:
            # Use quick model for fast extraction
            model = self.quick_model or self.model

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": 1024,  # Quick tier needs less output
                            "num_ctx": 8192,  # Quick tier uses less context
                        }
                    }
                )

                elapsed = time.time() - start_time

                if response.status_code != 200:
                    return PaperExtraction(
                        paper_id=paper_id,
                        success=False,
                        error=f"Ollama error: {response.status_code}",
                        elapsed_seconds=elapsed,
                        prompt_used=prompt if verbose else None
                    )

                data = response.json()
                response_text = data.get("response", "")

                # Parse using unified parser
                parsed = parse_extraction_response(response_text)

                # Validate quick tier schema
                is_valid, missing = validate_extraction(parsed, "quick")

                if not is_valid:
                    return PaperExtraction(
                        paper_id=paper_id,
                        success=False,
                        error=f"Missing required fields: {missing}",
                        elapsed_seconds=elapsed,
                        raw_response=response_text if verbose else None,
                        prompt_used=prompt if verbose else None
                    )

                extraction = PaperExtraction(
                    paper_id=paper_id,
                    paper_type=parsed.get("paper_type"),
                    topics=parsed.get("topics", []),
                    one_sentence_summary=parsed.get("one_sentence_summary"),
                    extractor_model=f"ollama/{model}",
                    elapsed_seconds=elapsed,
                    success=True
                )

                if verbose:
                    extraction.raw_response = response_text
                    extraction.prompt_used = prompt

                return extraction

        except httpx.TimeoutException:
            elapsed = time.time() - start_time
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error="Ollama timeout",
                elapsed_seconds=elapsed,
                prompt_used=prompt if verbose else None
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=str(e),
                elapsed_seconds=elapsed,
                prompt_used=prompt if verbose else None
            )

    async def extract_chunk(
        self,
        title: str,
        chunk_text: str,
        chunk_number: int,
        total_chunks: int,
        state: Optional["ChunkProcessingState"] = None,
    ) -> dict:
        """Extract information from a single chunk (deep extraction pass 1).

        Args:
            title: Paper title
            chunk_text: Text content of this chunk
            chunk_number: 1-indexed chunk number
            total_chunks: Total number of chunks
            state: Optional accumulated state from earlier chunks (facts-only
                forward context - glossary, sections seen). None means no
                prior context is injected into the prompt.

        Returns:
            Parsed chunk extraction dict or empty dict on failure
        """
        prompt = get_chunk_extraction_prompt(
            title=title,
            chunk_text=chunk_text,
            chunk_number=chunk_number,
            total_chunks=total_chunks,
            prior_context=state.to_prompt_context() if state else "",
        )

        # Use deep model for chunk extraction (part of deep pipeline)
        model = self.deep_model or self.model

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": 1024,
                            "num_ctx": settings.ollama.chunk_num_ctx,
                        }
                    }
                )

                if response.status_code != 200:
                    logger.warning(f"Chunk {chunk_number} extraction failed: {response.status_code}")
                    return {}

                data = response.json()
                response_text = data.get("response", "")
                return parse_extraction_response(response_text)

        except Exception as e:
            logger.warning(f"Chunk {chunk_number} extraction error: {e}")
            return {}

    async def extract_deep(
        self,
        title: str,
        abstract: str,
        chunks: list[str],
        quick_extraction: dict,
        journal: Optional[str] = None,
        authors: Optional[str] = None,
        year: Optional[int] = None,
        paper_id: int = 0,
        verbose: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
        corrections: Optional[str] = None
    ) -> PaperExtraction:
        """Extract deep tier using 2-pass approach (chunks → consolidation).

        Args:
            title: Paper title
            abstract: Paper abstract
            chunks: List of text chunks from PDF
            quick_extraction: Dict from quick extraction for verification
            journal: Journal name
            authors: Author names
            year: Publication year
            paper_id: Paper ID for the result
            verbose: If True, include detailed extraction info
            progress_callback: Optional callback (pass_num, current, total, message)
                pass 1 = chunk extraction, pass 2 = consolidation
            corrections: Optional feedback from a previous failed verification
                attempt, passed through to the consolidation prompt.

        Returns:
            PaperExtraction with full deep schema
        """
        import time
        start_time = time.time()

        # Load any prior checkpoint (facts-only glossary/sections carry forward);
        # chunk *results* are never persisted, so we always reprocess every chunk -
        # only chunks_processed is reset, glossary/sections_seen are kept.
        state = ChunkProcessingState.load_checkpoint(paper_id) or ChunkProcessingState(paper_id=paper_id)
        state.chunks_processed = 0

        # Pass 1: Extract from each chunk
        logger.info(f"Deep extraction pass 1: processing {len(chunks)} chunks")
        if progress_callback:
            progress_callback(1, 0, len(chunks), "Starting chunk extraction")

        chunk_extractions = []
        for i, chunk_text in enumerate(chunks, 1):
            if progress_callback:
                progress_callback(1, i, len(chunks), f"Extracting chunk {i}/{len(chunks)}")

            chunk_result = await self.extract_chunk(
                title=title,
                chunk_text=chunk_text,
                chunk_number=i,
                total_chunks=len(chunks),
                state=state,
            )
            chunk_extractions.append(chunk_result)
            state.update_from_chunk(chunk_result)
            if paper_id:
                state.save_checkpoint()
            # Log progress for long extractions
            if i % 5 == 0:
                logger.info(f"Processed {i}/{len(chunks)} chunks")

        # Pass 2: Consolidate all chunk extractions
        logger.info("Deep extraction pass 2: consolidating chunks")
        if progress_callback:
            progress_callback(2, 0, 1, "Consolidating chunk extractions")

        prompt = get_consolidation_prompt(
            title=title,
            abstract=abstract or "",
            quick_extraction=quick_extraction,
            chunk_extractions=chunk_extractions,
            journal=journal,
            authors=authors,
            year=year,
            corrections=corrections,
        )

        # Use deep model for full extraction
        model = self.deep_model or self.model

        est_tokens = len(prompt) // 3
        if est_tokens > settings.ollama.consolidation_num_ctx:
            logger.warning(
                "Consolidation prompt may exceed num_ctx",
                extra={
                    "paper_id": paper_id,
                    "est_tokens": est_tokens,
                    "num_ctx": settings.ollama.consolidation_num_ctx,
                },
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": 2048,  # Deep tier output
                            "num_ctx": settings.ollama.consolidation_num_ctx,
                        }
                    }
                )

                elapsed = time.time() - start_time

                if response.status_code != 200:
                    return PaperExtraction(
                        paper_id=paper_id,
                        success=False,
                        error=f"Ollama consolidation error: {response.status_code}",
                        elapsed_seconds=elapsed,
                        prompt_used=prompt if verbose else None
                    )

                data = response.json()
                response_text = data.get("response", "")

                # Parse using unified parser
                parsed = parse_extraction_response(response_text)

                # Validate deep tier schema
                is_valid, missing = validate_extraction(parsed, "deep")

                if not is_valid:
                    logger.warning(f"Deep extraction missing fields: {missing}")
                    # Continue anyway - partial extraction is still useful

                extraction = PaperExtraction(
                    paper_id=paper_id,
                    paper_type=parsed.get("paper_type"),
                    topics=parsed.get("topics", []),
                    one_sentence_summary=parsed.get("one_sentence_summary"),
                    key_findings=parsed.get("key_findings", []),
                    methodology_summary=parsed.get("methodology_summary"),
                    research_context=parsed.get("research_context"),
                    discussion_summary=parsed.get("discussion_summary"),
                    future_directions=parsed.get("future_directions", []),
                    quantitative_results=parsed.get("quantitative_results", []),
                    citable_claims=parsed.get("citable_claims", []),
                    techniques_used=parsed.get("techniques_used", []),
                    experimental_conditions=parsed.get("experimental_conditions"),
                    prior_work_comparison=parsed.get("prior_work_comparison", []),
                    citation_contexts=parsed.get("citation_contexts"),
                    chunk_extractions=chunk_extractions,  # For claim citation processing
                    extractor_model=f"ollama/{model}",
                    elapsed_seconds=elapsed,
                    success=True
                )

                if verbose:
                    extraction.raw_response = response_text
                    extraction.prompt_used = prompt

                # Extraction succeeded end-to-end - clear the checkpoint so a
                # future run doesn't carry stale state forward.
                if paper_id:
                    try:
                        from literature_core import get_session as _get_session
                        from literature_core.models import ExtractionMetadata as _ExtractionMetadata
                        with _get_session() as _session:
                            _meta = _session.query(_ExtractionMetadata).filter_by(paper_id=paper_id).first()
                            if _meta:
                                _meta.extraction_checkpoint = None
                                _session.commit()
                    except Exception as clear_exc:
                        logger.warning(
                            "Failed to clear extraction checkpoint",
                            extra={"paper_id": paper_id, "error": str(clear_exc)},
                        )

                return extraction

        except httpx.TimeoutException:
            elapsed = time.time() - start_time
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error="Ollama consolidation timeout",
                elapsed_seconds=elapsed,
                prompt_used=prompt if verbose else None
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return PaperExtraction(
                paper_id=paper_id,
                success=False,
                error=str(e),
                elapsed_seconds=elapsed,
                prompt_used=prompt if verbose else None
            )


# =============================================================================
# Extraction Service
# =============================================================================

class ExtractionService:
    """Service for AI-powered paper extraction."""

    # Default LLM preference order (local only)
    LLM_PREFERENCE = ["ollama"]

    @classmethod
    def get_extraction_status(cls) -> ExtractionStatus:
        """Get extraction coverage statistics.

        Returns:
            ExtractionStatus with coverage statistics
        """
        with get_session() as session:
            status = ExtractionStatus()

            status.total_papers = session.query(Paper).count()

            # Count papers with chunks (Paper.full_text column is deprecated)
            papers_with_chunks = set(
                p[0] for p in session.query(PaperChunk.paper_id).distinct().all()
            )
            status.papers_with_full_text = len(papers_with_chunks)

            status.papers_with_abstract = session.query(Paper).filter(
                Paper.abstract.isnot(None),
                Paper.abstract != ''
            ).count()

            status.papers_with_extraction = session.query(PaperContent).count()

            # Papers needing extraction: have content but no extraction
            # Include papers with chunks or legacy full_text or abstract
            papers_with_abstract_ids = set(
                p.id for p in session.query(Paper.id).filter(
                    Paper.abstract.isnot(None),
                    Paper.abstract != ''
                ).all()
            )
            extractable_ids_set = papers_with_chunks | papers_with_abstract_ids
            extractable_ids = session.query(Paper.id).filter(
                Paper.id.in_(extractable_ids_set)
            ).scalar_subquery()

            extracted_ids = session.query(PaperContent.paper_id).scalar_subquery()

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
            extracted_ids = session.query(PaperContent.paper_id).scalar_subquery()

            # Get IDs of papers with chunks (Paper.full_text column is deprecated)
            papers_with_chunks = set(
                p[0] for p in session.query(PaperChunk.paper_id).distinct().all()
            )

            query = session.query(Paper).filter(
                ~Paper.id.in_(extracted_ids),
                (Paper.id.in_(papers_with_chunks)) |
                (Paper.abstract.isnot(None) & (Paper.abstract != ''))
            )

            if prioritize_full_text:
                # Prioritize papers with chunks (full text)
                query = query.order_by(
                    ~Paper.id.in_(papers_with_chunks),  # Papers with chunks first
                    Paper.date_added.desc()
                )
            else:
                query = query.order_by(Paper.date_added.desc())

            papers = query.limit(limit).all()

            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "has_full_text": p.id in papers_with_chunks,
                    "has_abstract": bool(p.abstract),
                    "year": p.year,
                }
                for p in papers
            ]

    @classmethod
    def get_papers_with_extractions(
        cls,
        limit: int = 50,
        older_than_days: int | None = None,
        schema_version: str | None = None,
        extractor_model: str | None = None,
    ) -> list[dict]:
        """Get papers that have existing extractions (for re-extraction).

        Useful for finding papers to re-extract with updated models or schemas.

        Args:
            limit: Maximum papers to return
            older_than_days: Only include extractions older than N days
            schema_version: Only include extractions with this schema version
            extractor_model: Only include extractions from this model (partial match)

        Returns:
            List of paper dicts with extraction metadata
        """
        from datetime import datetime, timedelta

        with get_session() as session:
            query = session.query(
                Paper.id,
                Paper.title,
                Paper.year,
                PaperContent.extraction_date,
                PaperContent.schema_version,
                PaperContent.extractor_model,
            ).join(
                PaperContent, Paper.id == PaperContent.paper_id
            )

            # Filter by age
            if older_than_days is not None:
                cutoff = datetime.utcnow() - timedelta(days=older_than_days)
                query = query.filter(PaperContent.extraction_date < cutoff)

            # Filter by schema version
            if schema_version:
                query = query.filter(PaperContent.schema_version == schema_version)

            # Filter by extractor model (partial match)
            if extractor_model:
                query = query.filter(
                    PaperContent.extractor_model.ilike(f"%{extractor_model}%")
                )

            # Order by extraction date (oldest first for re-extraction)
            query = query.order_by(PaperContent.extraction_date.asc())

            results = query.limit(limit).all()

            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "year": r.year,
                    "extraction_date": r.extraction_date.isoformat() if r.extraction_date else None,
                    "schema_version": r.schema_version,
                    "extractor_model": r.extractor_model,
                }
                for r in results
            ]

    @classmethod
    def get_llm_status(cls) -> dict:
        """Get status of available LLM backends (local only).

        Returns:
            Dict with availability status for each backend
        """
        ollama = OllamaClient()

        return {
            "ollama": {
                "available": ollama.is_available(),
                "model": settings.ollama.reader_model,
                "host": settings.ollama.host,
            },
            "recommended": "ollama" if ollama.is_available() else None
        }

    @classmethod
    async def extract_paper(
        cls,
        paper_id: int,
        backend: Literal["ollama", "auto"] = "auto",
        force: bool = False,
        verbose: bool = False
    ) -> PaperExtraction:
        """Extract structured content from a paper.

        Args:
            paper_id: Paper ID to extract
            backend: LLM backend to use (ollama or auto) - local only
            force: If True, re-extract even if extraction exists
            verbose: If True, include raw_response and prompt_used in result

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

            # Get full text from chunks (Paper.full_text column is deprecated)
            full_text = PaperService.get_full_text(paper_id, session)

            # Check if paper has extractable content
            if not paper.abstract and not full_text:
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
                full_text=full_text,
                paper_id=paper_id,
                verbose=verbose
            )

            # Store if successful
            if extraction.success:
                cls._store_extraction(session, paper_id, extraction)

            return extraction

    @classmethod
    async def extract_paper_quick(
        cls,
        paper_id: int,
        backend: Literal["ollama", "auto"] = "auto",
        force: bool = False,
        verbose: bool = False
    ) -> PaperExtraction:
        """Extract quick tier (abstract-only) for fast categorization.

        Quick extraction provides paper_type, topics, and one_sentence_summary.
        Use this for all papers when first added to enable search and filtering.

        Args:
            paper_id: Paper ID to extract
            backend: LLM backend (ollama or auto)
            force: If True, re-extract even if extraction exists
            verbose: If True, include raw_response and prompt_used

        Returns:
            PaperExtraction with quick tier fields
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
                if existing and existing.paper_type:
                    return PaperExtraction(
                        paper_id=paper_id,
                        paper_type=existing.paper_type,
                        topics=existing.topics,
                        one_sentence_summary=existing.one_sentence_summary,
                        extractor_model=existing.extractor_model,
                        success=True,
                        error="Already extracted (use force=true to re-extract)"
                    )

            # Quick extraction only needs abstract
            if not paper.abstract:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="Paper has no abstract for quick extraction"
                )

            # Get LLM client
            client = cls._get_client(backend)
            if not client:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="No LLM backend available"
                )

            # Extract using quick tier
            extraction = await client.extract_quick(
                title=paper.title,
                abstract=paper.abstract,
                journal=paper.journal,
                paper_id=paper_id,
                verbose=verbose
            )

            # Store if successful (quick tier)
            if extraction.success:
                cls._store_extraction(session, paper_id, extraction, is_quick=True)

            return extraction

    @classmethod
    async def extract_paper_deep(
        cls,
        paper_id: int,
        backend: Literal["ollama", "auto"] = "auto",
        force: bool = False,
        verbose: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
        corrections: Optional[str] = None
    ) -> PaperExtraction:
        """Extract deep tier using 2-pass approach (chunks → consolidation).

        Deep extraction requires:
        1. Existing quick extraction (for verification)
        2. PDF chunks (from extract_pdf_and_store)

        The 2-pass approach:
        - Pass 1: Extract from each chunk separately
        - Pass 2: Consolidate all chunk extractions into final schema

        Args:
            paper_id: Paper ID to extract
            backend: LLM backend (ollama or auto)
            force: If True, re-extract even if deep extraction exists
            verbose: If True, include detailed extraction info
            progress_callback: Optional callback (pass_num, current, total, message)
            corrections: Optional feedback from a previous failed verification
                attempt, passed through to the consolidation prompt.

        Returns:
            PaperExtraction with full deep schema
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="Paper not found"
                )

            # Check if deep extraction already exists
            if not force:
                existing = session.query(PaperContent).filter(
                    PaperContent.paper_id == paper_id
                ).first()
                if existing and existing.key_findings:
                    # Has deep extraction (key_findings is a deep-tier field)
                    return PaperExtraction(
                        paper_id=paper_id,
                        paper_type=existing.paper_type,
                        topics=existing.topics,
                        one_sentence_summary=existing.one_sentence_summary,
                        key_findings=existing.key_findings,
                        methodology_summary=existing.methodology_summary,
                        extractor_model=existing.extractor_model,
                        success=True,
                        error="Already has deep extraction (use force=true to re-extract)"
                    )

            # Get chunks for deep extraction
            chunks = session.query(PaperChunk).filter(
                PaperChunk.paper_id == paper_id
            ).order_by(PaperChunk.chunk_order).all()

            if not chunks:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="Paper has no chunks. Run extract_pdf_and_store first."
                )

            # Get quick extraction for verification
            existing_content = session.query(PaperContent).filter(
                PaperContent.paper_id == paper_id
            ).first()

            quick_extraction = {}
            if existing_content:
                quick_extraction = {
                    "paper_type": existing_content.paper_type,
                    "topics": existing_content.topics,
                    "one_sentence_summary": existing_content.one_sentence_summary,
                }
            else:
                # Run quick extraction first
                logger.info(f"Running quick extraction first for paper {paper_id}")
                quick_result = await cls.extract_paper_quick(
                    paper_id, backend=backend, verbose=verbose
                )
                if quick_result.success:
                    quick_extraction = {
                        "paper_type": quick_result.paper_type,
                        "topics": quick_result.topics,
                        "one_sentence_summary": quick_result.one_sentence_summary,
                    }

            # Get LLM client
            client = cls._get_client(backend)
            if not client:
                return PaperExtraction(
                    paper_id=paper_id,
                    success=False,
                    error="No LLM backend available"
                )

            # Get author names
            authors = ", ".join(a.name for a in paper.authors) if paper.authors else None

            # Extract using deep tier (2-pass)
            chunk_texts = [c.content for c in chunks]
            extraction = await client.extract_deep(
                title=paper.title,
                abstract=paper.abstract or "",
                chunks=chunk_texts,
                quick_extraction=quick_extraction,
                journal=paper.journal,
                authors=authors,
                year=paper.year,
                paper_id=paper_id,
                verbose=verbose,
                progress_callback=progress_callback,
                corrections=corrections
            )

            # Store if successful (deep tier)
            if extraction.success:
                cls._store_extraction(session, paper_id, extraction, is_quick=False)

                # Process claim citations from chunk extractions
                if extraction.chunk_extractions:
                    cls._process_claim_citations(
                        session, paper_id, extraction.chunk_extractions
                    )

            return extraction

    @classmethod
    def _get_client(cls, backend: str) -> Optional[LLMClient]:
        """Get an LLM client based on preference (local only)."""
        ollama = OllamaClient()

        if backend == "ollama" or backend == "auto":
            return ollama if ollama.is_available() else None
        return None

    @classmethod
    def _store_extraction(
        cls,
        session,
        paper_id: int,
        extraction: PaperExtraction,
        is_quick: bool = False
    ) -> None:
        """Store extraction in database and update enrichment status.

        Args:
            session: Database session
            paper_id: Paper ID
            extraction: PaperExtraction dataclass with extracted data
            is_quick: If True, this is a quick (abstract-only) extraction
        """
        # Build structured_data for extended fields
        structured_data = {}
        if extraction.research_context:
            structured_data["research_context"] = extraction.research_context
        if extraction.discussion_summary:
            structured_data["discussion_summary"] = extraction.discussion_summary
        if extraction.future_directions:
            structured_data["future_directions"] = extraction.future_directions
        # New citation-matching fields
        if extraction.quantitative_results:
            structured_data["quantitative_results"] = extraction.quantitative_results
        if extraction.citable_claims:
            structured_data["citable_claims"] = extraction.citable_claims
        if extraction.techniques_used:
            structured_data["techniques_used"] = extraction.techniques_used
        if extraction.experimental_conditions:
            structured_data["experimental_conditions"] = extraction.experimental_conditions
        if extraction.prior_work_comparison:
            structured_data["prior_work_comparison"] = extraction.prior_work_comparison
        if extraction.citation_contexts:
            structured_data["citation_contexts"] = extraction.citation_contexts
        if extraction.cited_references:
            structured_data["cited_references"] = extraction.cited_references

        # Determine extraction depth and date field
        extraction_depth = "abstract_only" if is_quick else "comprehensive"
        now = datetime.utcnow()

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
            content.extraction_depth = extraction_depth
            content.schema_version = "2.0"
            if is_quick:
                content.quick_extraction_date = now
            else:
                content.deep_extraction_date = now
            if structured_data:
                content.structured_data = structured_data
        else:
            content = PaperContent(
                paper_id=paper_id,
                paper_type=extraction.paper_type,
                topics=extraction.topics,
                one_sentence_summary=extraction.one_sentence_summary,
                key_findings=extraction.key_findings,
                methodology_summary=extraction.methodology_summary,
                extractor_model=extraction.extractor_model,
                extraction_depth=extraction_depth,
                schema_version="2.0",
                quick_extraction_date=now if is_quick else None,
                deep_extraction_date=now if not is_quick else None,
                structured_data=structured_data if structured_data else None,
            )
            session.add(content)

        # Update paper enrichment status
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if paper:
            # Both quick and deep extraction mark as complete
            paper.enrichment_status = EnrichmentStatus.COMPLETE

        session.commit()
        logger.info(f"Stored {extraction_depth} extraction for paper {paper_id}")

    @classmethod
    def _process_claim_citations(
        cls,
        session,
        paper_id: int,
        chunk_extractions: list[dict],
    ) -> int:
        """Process claim citations from chunk extractions and store in database.

        Links extracted claims to references in the paper's bibliography and
        to matching papers in the library.

        Args:
            session: Database session
            paper_id: Paper ID
            chunk_extractions: List of dicts from chunk extraction pass

        Returns:
            Number of claim citations stored
        """
        from literature_core import ClaimCitation, PaperReference

        # Get paper with its references
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            logger.warning(f"Cannot process claim citations: paper {paper_id} not found")
            return 0

        # Build reference lookup by reference_order (citation number)
        references = {}
        for ref in session.query(PaperReference).filter(
            PaperReference.paper_id == paper_id
        ).all():
            if ref.reference_order is not None:
                references[ref.reference_order] = ref

        # Clear existing claim citations for this paper
        session.query(ClaimCitation).filter(
            ClaimCitation.paper_id == paper_id
        ).delete()

        claims_stored = 0

        # Process each chunk's claim citations
        for chunk_idx, chunk_data in enumerate(chunk_extractions):
            claim_citations = chunk_data.get("claim_citations", [])
            section_type = chunk_data.get("section_type")

            for claim_data in claim_citations:
                if not isinstance(claim_data, dict):
                    continue

                claim_text = claim_data.get("claim")
                citation_numbers = claim_data.get("citation_numbers", [])
                claim_type = claim_data.get("claim_type")
                importance = claim_data.get("importance")

                if not claim_text or not citation_numbers:
                    continue

                # Ensure citation_numbers is a list of integers
                if not isinstance(citation_numbers, list):
                    continue
                citation_numbers = [int(n) for n in citation_numbers if isinstance(n, (int, float))]

                if not citation_numbers:
                    continue

                # Match citation numbers to references and library papers
                reference_ids = []
                matched_paper_ids = []
                match_statuses = []

                for num in citation_numbers:
                    # Citation numbers in papers are 1-indexed, but references are stored 0-indexed
                    # So citation [1] maps to reference_order 0
                    ref = references.get(num - 1) if num > 0 else None
                    if ref:
                        reference_ids.append(ref.id)
                        if ref.matched_paper_id:
                            matched_paper_ids.append(ref.matched_paper_id)
                            match_statuses.append("matched")
                        else:
                            matched_paper_ids.append(None)
                            match_statuses.append("unmatched")
                    else:
                        reference_ids.append(None)
                        matched_paper_ids.append(None)
                        match_statuses.append("reference_not_found")

                # Create claim citation record
                claim = ClaimCitation(
                    paper_id=paper_id,
                    claim_text=claim_text[:2000] if claim_text else "",  # Truncate if too long
                    citation_numbers=citation_numbers,
                    section=section_type,
                    chunk_index=chunk_idx,
                    claim_type=claim_type,
                    reference_ids=reference_ids,
                    matched_paper_ids=matched_paper_ids,
                    match_statuses=match_statuses,
                    importance=importance,
                )
                session.add(claim)
                claims_stored += 1

        if claims_stored > 0:
            logger.info(f"Stored {claims_stored} claim citations for paper {paper_id}")

        return claims_stored

    @classmethod
    async def extract_batch(
        cls,
        paper_ids: list[int] | None = None,
        limit: int = 10,
        backend: Literal["ollama", "auto"] = "auto",
        delay: float = 1.0,
        force: bool = False
    ) -> ExtractionResult:
        """Extract multiple papers.

        Args:
            paper_ids: Specific papers to extract, or None to use queue
            limit: Maximum papers from queue if no IDs specified
            backend: LLM backend to use (local only: ollama)
            delay: Seconds between extractions (rate limiting)
            force: If True, re-extract papers that already have extractions

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
                    backend=backend,
                    force=force
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
                logger.info(f"Deleted extraction for paper {paper_id}")
                return True

            return False

    # ILL/Library contamination patterns
    ILL_PATTERNS = [
        "interlibrary loan",
        "document delivery",
        "illiad",
        "loansome doc",
        "university of washington libraries",
        "copyright notice",
        "this document may not be posted",
    ]

    @classmethod
    def assess_text_quality(
        cls,
        full_text: Optional[str],
        abstract: Optional[str] = None,
        word_count: int = 0
    ) -> dict:
        """Assess the quality of extracted text.

        Checks for:
        - ILL/library cover page contamination
        - Missing abstract with full text present
        - Suspiciously low word count
        - Text starting with metadata instead of content

        Args:
            full_text: The extracted full text
            abstract: The paper's abstract (if any)
            word_count: Total word count

        Returns:
            Dict with quality assessment:
            {
                "quality": "good" | "contaminated" | "suspect",
                "issues": [...],
                "recommendation": "text" | "vision" | "enrich"
            }
        """
        issues = []
        recommendation = "text"  # Default: use text extraction

        if not full_text:
            return {
                "quality": "missing",
                "issues": ["No full text available"],
                "recommendation": "enrich"
            }

        text_lower = full_text[:2000].lower()  # Check first 2000 chars

        # Check for ILL contamination
        for pattern in cls.ILL_PATTERNS:
            if pattern in text_lower:
                issues.append(f"ILL contamination detected: '{pattern}'")
                recommendation = "vision"
                break

        # Check if abstract is missing but full text exists
        if not abstract and full_text and len(full_text) > 1000:
            # This might indicate the abstract wasn't extracted properly
            issues.append("No abstract despite having full text")
            if recommendation != "vision":
                recommendation = "enrich"

        # Check for suspiciously low word count (e.g., OCR failures)
        if word_count > 0 and word_count < 500 and len(full_text) > 5000:
            issues.append(f"Low word count ({word_count}) for text length")
            recommendation = "vision"

        # Check if text starts with metadata-like content
        first_lines = full_text[:500].lower()
        metadata_indicators = ["doi:", "issn:", "volume", "issue", "received", "accepted"]
        metadata_count = sum(1 for ind in metadata_indicators if ind in first_lines)
        if metadata_count >= 3:
            # This is fine - many papers start with metadata
            pass

        quality = "good" if not issues else ("contaminated" if "ILL" in str(issues) else "suspect")

        return {
            "quality": quality,
            "issues": issues,
            "recommendation": recommendation
        }

    @classmethod
    def get_papers_with_quality_issues(cls, limit: int = 50) -> list[dict]:
        """Get papers that have text quality issues.

        Returns papers where text extraction may have problems
        (ILL contamination, missing abstracts, etc.)

        Args:
            limit: Maximum papers to return

        Returns:
            List of paper dicts with quality assessments
        """
        with get_session() as session:
            # Query papers with chunks (Paper.full_text column is deprecated)
            papers_with_chunks = (
                session.query(Paper)
                .filter(Paper.id.in_(
                    session.query(PaperChunk.paper_id).distinct()
                ))
                .limit(limit * 2)
                .all()
            )

            results = []
            for p in papers_with_chunks:
                # Get full text from chunks
                full_text = PaperService.get_full_text(p.id, session)
                if not full_text:
                    continue

                assessment = cls.assess_text_quality(
                    full_text=full_text,
                    abstract=p.abstract,
                    word_count=p.word_count or 0
                )

                if assessment["quality"] != "good":
                    results.append({
                        "id": p.id,
                        "title": p.title,
                        "year": p.year,
                        "has_abstract": bool(p.abstract),
                        "word_count": p.word_count,
                        **assessment
                    })

                if len(results) >= limit:
                    break

            return results

    # =========================================================================
    # PDF Processing Methods (from ChunkedExtractionService)
    # =========================================================================

    @staticmethod
    def extract_pdf_and_store(
        paper_id: int,
        force: bool = False,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        progress_callback: ProgressCallback | None = None,
    ) -> PDFExtractionResult:
        """Extract PDF and store as chunks.

        Args:
            paper_id: Paper ID
            force: Re-extract even if already done
            chunk_size: Target words per chunk
            progress_callback: Optional callback for progress updates

        Returns:
            PDFExtractionResult with extraction details
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return PDFExtractionResult(
                    success=False,
                    paper_id=paper_id,
                    error=f"Paper {paper_id} not found"
                )

            if not paper.file_path:
                return PDFExtractionResult(
                    success=False,
                    paper_id=paper_id,
                    error="Paper has no PDF"
                )

            pdf_path = Path(paper.file_path)
            if not pdf_path.exists():
                return PDFExtractionResult(
                    success=False,
                    paper_id=paper_id,
                    error=f"PDF not found: {pdf_path}"
                )

            # Check if already extracted
            existing = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            # Only skip if we have existing metadata WITH chunks extracted
            # If chunk_count is 0 or None, proceed with extraction even if metadata exists
            if existing and not force and (existing.chunk_count or 0) > 0:
                return PDFExtractionResult(
                    success=True,
                    paper_id=paper_id,
                    chunk_count=existing.chunk_count or 0,
                    table_count=existing.table_count or 0,
                    figure_count=existing.figure_count or 0,
                    word_count=existing.word_count or 0,
                    page_count=existing.page_count or 0,
                )

            # Calculate PDF hash
            pdf_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:16]

            # Extract content
            try:
                full_text, tables, figures, references, page_count = ExtractionService._extract_pdf(
                    pdf_path,
                    progress_callback=progress_callback,
                )
            except Exception as e:
                logger.error(f"PDF extraction failed for paper {paper_id}: {e}")
                return PDFExtractionResult(
                    success=False,
                    paper_id=paper_id,
                    error=str(e)
                )

            # Split into chunks
            chunks = ExtractionService._split_into_chunks(full_text, chunk_size)

            # Clear existing extraction data
            ExtractionService._clear_pdf_extraction(session, paper_id)

            # Store chunks
            for i, chunk_text in enumerate(chunks):
                chunk = PaperChunk(
                    paper_id=paper_id,
                    chunk_order=i,
                    content=chunk_text,
                    word_count=len(chunk_text.split()),
                    char_count=len(chunk_text),
                )
                session.add(chunk)

            # Store tables
            for i, (markdown, caption, rows, cols, page) in enumerate(tables):
                table = PaperTable(
                    paper_id=paper_id,
                    table_order=i,
                    markdown=markdown,
                    caption=caption,
                    row_count=rows,
                    col_count=cols,
                    page_number=page,
                )
                session.add(table)

            # Store figures
            for fig_type, fig_num, caption, page in figures:
                figure = PaperFigure(
                    paper_id=paper_id,
                    figure_type=fig_type,
                    figure_number=fig_num,
                    caption=caption,
                    page_number=page,
                )
                session.add(figure)

            # Store references
            for i, ref_data in enumerate(references):
                reference = PaperReference(
                    paper_id=paper_id,
                    reference_order=i,
                    raw_text=ref_data['raw_text'],
                    parsed_title=ref_data.get('title'),
                    parsed_authors=ref_data.get('authors'),
                    parsed_year=ref_data.get('year'),
                    parsed_journal=ref_data.get('journal'),
                    parsed_doi=ref_data.get('doi'),
                    parsed_arxiv_id=ref_data.get('arxiv_id'),
                    parse_confidence=ref_data.get('confidence', 0.5),
                )
                session.add(reference)

            # Store metadata
            word_count = sum(len(c.split()) for c in chunks)
            if existing:
                existing.extraction_method = 'pdfplumber'
                existing.chunk_count = len(chunks)
                existing.table_count = len(tables)
                existing.figure_count = len(figures)
                existing.reference_count = len(references)
                existing.word_count = word_count
                existing.page_count = page_count
                existing.pdf_hash = pdf_hash
                existing.needs_reextraction = 0
            else:
                metadata = ExtractionMetadata(
                    paper_id=paper_id,
                    extraction_method='pdfplumber',
                    chunk_count=len(chunks),
                    table_count=len(tables),
                    figure_count=len(figures),
                    reference_count=len(references),
                    word_count=word_count,
                    page_count=page_count,
                    pdf_hash=pdf_hash,
                )
                session.add(metadata)

            return PDFExtractionResult(
                success=True,
                paper_id=paper_id,
                chunk_count=len(chunks),
                table_count=len(tables),
                figure_count=len(figures),
                reference_count=len(references),
                word_count=word_count,
                page_count=page_count,
            )

    @staticmethod
    def _extract_pdf(
        pdf_path: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[str, list, list, list, int]:
        """Extract text, tables, figures, and references from PDF.

        Uses early detection to choose extraction strategy:
        - Samples first 5 pages to detect if PDF is scanned
        - If scanned: goes straight to OCR (no wasted text extraction)
        - If text-based: uses fast pdfplumber extraction

        Args:
            pdf_path: Path to PDF file
            progress_callback: Optional callback for progress updates

        Returns:
            (full_text, tables, figures, references, page_count)
        """
        def report(phase: str, detail: str, pct: int | None = None):
            if progress_callback:
                progress_callback(phase, detail, pct)

        report("detect", "Detecting PDF type...", 0)

        # Step 1: Sample first few pages to detect if scanned
        sample_size = 5
        sample_empty = 0
        page_count = 0

        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            pages_to_sample = min(sample_size, page_count)

            for i in range(pages_to_sample):
                text = pdf.pages[i].extract_text() or ""
                if not text.strip():
                    sample_empty += 1

        # Decide extraction strategy based on sample
        use_ocr = sample_empty >= (pages_to_sample * 0.8)  # 80% of sample empty → OCR

        if use_ocr:
            report("ocr", f"Scanned PDF detected ({sample_empty}/{pages_to_sample} sample pages empty)", 2)
            logger.info(f"PDF {pdf_path.name}: detected as scanned, using OCR")
            return ExtractionService._extract_pdf_ocr(pdf_path, page_count, progress_callback)
        else:
            report("text", f"Text PDF detected ({pages_to_sample - sample_empty}/{pages_to_sample} sample pages have text)", 2)
            return ExtractionService._extract_pdf_text(pdf_path, page_count, progress_callback)

    @staticmethod
    def _extract_pdf_text(
        pdf_path: Path,
        page_count: int,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[str, list, list, list, int]:
        """Extract text from PDF using pdfplumber (fast, for text-based PDFs)."""
        def report(phase: str, detail: str, pct: int | None = None):
            if progress_callback:
                progress_callback(phase, detail, pct)

        full_text_parts = []
        tables = []
        all_text_for_figures = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                pct = 5 + int((page_num / page_count) * 80)  # 5-85%
                report("text", f"Page {page_num}/{page_count}", pct)

                # Extract text
                text = page.extract_text() or ""
                if text.strip():
                    full_text_parts.append(f"[Page {page_num}]\n{text}")
                    all_text_for_figures.append(text)

                # Extract tables
                for table in page.extract_tables():
                    if table and len(table) > 1:
                        markdown = ExtractionService._table_to_markdown(table)
                        if markdown:
                            tables.append((
                                markdown,
                                None,
                                len(table),
                                len(table[0]) if table[0] else 0,
                                page_num,
                            ))

        full_text = "\n\n".join(full_text_parts)

        # Extract figure captions
        report("figures", "Extracting figures...", 88)
        figures = ExtractionService._extract_figure_captions("\n".join(all_text_for_figures))

        # Extract references
        report("references", "Extracting references...", 92)
        references = ExtractionService._extract_references(full_text)

        report("complete", f"Done: {len(full_text_parts)} pages, {len(tables)} tables", 100)
        return full_text, tables, figures, references, page_count

    @staticmethod
    def _extract_pdf_ocr(
        pdf_path: Path,
        page_count: int,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[str, list, list, list, int]:
        """Extract text from scanned PDF using OCR."""
        def report(phase: str, detail: str, pct: int | None = None):
            if progress_callback:
                progress_callback(phase, detail, pct)

        full_text_parts = []
        all_text_for_figures = []
        tables = []  # OCR doesn't extract tables well

        try:
            from pdf2image import convert_from_path
            import pytesseract

            # Convert PDF to images
            report("ocr", "Converting to images...", 5)
            images = convert_from_path(pdf_path, dpi=150)

            # OCR each page
            for page_num, image in enumerate(images, 1):
                pct = 10 + int((page_num / len(images)) * 75)  # 10-85%
                report("ocr", f"OCR page {page_num}/{len(images)}", pct)

                text = pytesseract.image_to_string(image, lang='eng')
                if text.strip():
                    full_text_parts.append(f"[Page {page_num}]\n{text}")
                    all_text_for_figures.append(text)

            logger.info(f"OCR extracted text from {len(full_text_parts)}/{len(images)} pages")

        except ImportError as e:
            report("ocr", f"OCR unavailable: {e}", None)
            logger.warning(f"OCR dependencies not available: {e}")
        except Exception as e:
            report("ocr", f"OCR failed: {e}", None)
            logger.warning(f"OCR failed: {e}")

        full_text = "\n\n".join(full_text_parts)

        # Extract figure captions
        report("figures", "Extracting figures...", 88)
        figures = ExtractionService._extract_figure_captions("\n".join(all_text_for_figures))

        # Extract references
        report("references", "Extracting references...", 92)
        references = ExtractionService._extract_references(full_text)

        report("complete", f"Done: {len(full_text_parts)} pages (OCR)", 100)
        return full_text, tables, figures, references, page_count

    @staticmethod
    def _table_to_markdown(table: list[list]) -> str | None:
        """Convert pdfplumber table to markdown."""
        if not table or len(table) < 2:
            return None

        # Clean cells
        def clean_cell(cell):
            if cell is None:
                return ""
            return str(cell).replace("\n", " ").strip()

        rows = [[clean_cell(c) for c in row] for row in table]

        # Skip tables that are mostly empty
        non_empty = sum(1 for row in rows for cell in row if cell)
        if non_empty < 3:
            return None

        # Build markdown
        lines = []
        # Header
        lines.append("| " + " | ".join(rows[0]) + " |")
        lines.append("| " + " | ".join(["---"] * len(rows[0])) + " |")
        # Data rows
        for row in rows[1:]:
            # Pad row if needed
            while len(row) < len(rows[0]):
                row.append("")
            lines.append("| " + " | ".join(row[:len(rows[0])]) + " |")

        return "\n".join(lines)

    @staticmethod
    def _extract_figure_captions(text: str) -> list[tuple[str, str, str, int | None]]:
        """Extract figure and table captions from text.

        Returns:
            List of (figure_type, figure_number, caption, page_number)
        """
        figures = []

        # Pattern for Figure/Fig. X. Caption or Table X. Caption
        pattern = (
            r'(?:^|\n)\s*((?:Figure|Fig\.|Table|Scheme)\s*'
            r'(\d+[a-z]?(?:[-–]\d+[a-z]?)?)[.:]\s*'
            r'([^\n]+(?:\n(?![A-Z]|\d+\.|Figure|Fig\.|Table|Scheme)[^\n]+)*))'
        )

        for match in re.finditer(pattern, text, re.IGNORECASE):
            full_match = match.group(1)
            fig_type = "figure"
            if full_match.lower().startswith("table"):
                fig_type = "table"
            elif full_match.lower().startswith("scheme"):
                fig_type = "scheme"

            fig_num = match.group(2).strip()
            caption = match.group(3).strip()

            # Clean up caption
            caption = re.sub(r'\s+', ' ', caption)

            if len(caption) > 10:  # Skip very short captions
                figures.append((fig_type, fig_num, caption, None))

        return figures

    @staticmethod
    def _extract_references(text: str) -> list[dict]:
        """Extract references from the bibliography section.

        Finds the references section and parses individual citations.

        Returns:
            List of dicts with raw_text and parsed fields (title, authors, year, doi, etc.)
        """
        references = []

        # Find references section using common headers
        ref_section_patterns = [
            r'\n(?:References|Bibliography|Literature Cited|Works Cited)\s*\n',
            r'\n(?:REFERENCES|BIBLIOGRAPHY)\s*\n',
        ]

        ref_text = None
        for pattern in ref_section_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get text from this point to the end (or next major section)
                ref_text = text[match.end():]
                # Try to find end of references (acknowledgments, appendix, etc.)
                end_match = re.search(
                    r'\n(?:Acknowledgment|Appendix|Supporting Information|Supplementary)\s*\n',
                    ref_text, re.IGNORECASE
                )
                if end_match:
                    ref_text = ref_text[:end_match.start()]
                break

        if not ref_text:
            return references

        # Split into individual references
        # Handle numbered references [1], 1., (1)
        numbered_pattern = r'(?:^|\n)\s*(?:\[(\d+)\]|(\d+)\.|(?:\((\d+)\)))\s*'
        numbered_refs = re.split(numbered_pattern, ref_text)

        # If numbered splitting worked, process those
        if len(numbered_refs) > 2:
            i = 1  # Skip first empty split
            while i < len(numbered_refs):
                # Find the reference number
                # Skip the three capture groups for reference number
                i += 3
                if i < len(numbered_refs):
                    raw = numbered_refs[i].strip()
                    if raw and len(raw) > 20:  # Skip very short fragments
                        parsed = ExtractionService._parse_reference(raw)
                        references.append(parsed)
                    i += 1
        else:
            # Fall back to paragraph splitting for non-numbered references
            paragraphs = re.split(r'\n\s*\n', ref_text)
            for para in paragraphs:
                raw = para.strip()
                if raw and len(raw) > 30:  # Minimum length for valid reference
                    parsed = ExtractionService._parse_reference(raw)
                    references.append(parsed)

        return references

    @staticmethod
    def _parse_reference(raw_text: str) -> dict:
        """Parse a single reference string to extract structured data.

        Args:
            raw_text: Raw reference text

        Returns:
            Dict with raw_text and parsed fields
        """
        result = {'raw_text': raw_text, 'confidence': 0.5}

        # Clean up the text
        text = re.sub(r'\s+', ' ', raw_text).strip()

        # Extract DOI
        doi_match = re.search(
            r'(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,}/[^\s,]+)',
            text, re.IGNORECASE
        )
        if doi_match:
            result['doi'] = doi_match.group(1).rstrip('.')
            result['confidence'] = 0.9

        # Extract arXiv ID
        arxiv_match = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5}(?:v\d+)?)', text, re.IGNORECASE)
        if arxiv_match:
            result['arxiv_id'] = arxiv_match.group(1)
            result['confidence'] = max(result['confidence'], 0.85)

        # Extract year (4-digit number, typically in parentheses or after authors)
        year_match = re.search(r'[(\s](\d{4})[)\s,.]', text)
        if year_match:
            year = int(year_match.group(1))
            if 1900 <= year <= 2030:
                result['year'] = year

        # Try to extract title (usually in quotes or after year, before journal)
        # Common patterns: "Title" or Title. Journal
        title_match = re.search(r'["""]([^"""]+)["""]', text)
        if title_match:
            result['title'] = title_match.group(1).strip()
        else:
            # Try to find title after year - typically ends at journal name
            # This is a rough heuristic
            journal_indicators = ['Journal', 'Proceedings', 'Conference', 'Trans.', 'Lett.']
            for indicator in journal_indicators:
                idx = text.find(indicator)
                if idx > 0:
                    # Title is likely between year and journal
                    potential_title = text[:idx].strip()
                    # Remove author part (usually before year)
                    if result.get('year'):
                        year_idx = potential_title.find(str(result['year']))
                        if year_idx > 0:
                            potential_title = potential_title[year_idx+4:].strip(' .,')
                    if len(potential_title) > 10:
                        result['title'] = potential_title[:300]  # Cap title length
                    break

        # Extract journal (look for italics markers or common patterns)
        journal_match = re.search(
            r'(?:in\s+)?(?:Proc(?:eedings)?\.?\s+of\s+)?([A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+)*)',
            text
        )
        if journal_match and len(journal_match.group(1)) > 3:
            result['journal'] = journal_match.group(1)[:200]

        # Extract authors (usually at the beginning, before year)
        if result.get('year'):
            year_str = str(result['year'])
            year_idx = text.find(year_str)
            if year_idx > 5:
                authors_part = text[:year_idx].strip(' .,')
                # Clean up author string
                authors_part = re.sub(r'\s+', ' ', authors_part)
                if len(authors_part) > 3 and len(authors_part) < 500:
                    result['authors'] = authors_part

        return result

    # =========================================================================
    # Section-Aware Chunking
    # =========================================================================

    # Common section header patterns (case-insensitive)
    SECTION_PATTERNS = [
        # Standard IMRaD sections
        (r'^(?:\d+\.?\s*)?abstract\b', 'Abstract', 0.9),
        (r'^(?:\d+\.?\s*)?introduction\b', 'Introduction', 0.9),
        (r'^(?:\d+\.?\s*)?background\b', 'Background', 0.8),
        (r'^(?:\d+\.?\s*)?(?:materials?\s+and\s+)?methods?\b', 'Methods', 0.9),
        (r'^(?:\d+\.?\s*)?experimental\s+(?:section|methods?|details?|procedures?)\b', 'Methods', 0.85),
        (r'^(?:\d+\.?\s*)?results?\b', 'Results', 0.9),
        (r'^(?:\d+\.?\s*)?results?\s+and\s+discussion\b', 'Results and Discussion', 0.9),
        (r'^(?:\d+\.?\s*)?discussion\b', 'Discussion', 0.9),
        (r'^(?:\d+\.?\s*)?conclusions?\b', 'Conclusion', 0.9),
        (r'^(?:\d+\.?\s*)?summary\b', 'Summary', 0.8),
        (r'^(?:\d+\.?\s*)?references?\b', 'References', 0.95),
        (r'^(?:\d+\.?\s*)?bibliography\b', 'References', 0.9),
        (r'^(?:\d+\.?\s*)?acknowledg(?:e)?ments?\b', 'Acknowledgments', 0.85),
        (r'^(?:\d+\.?\s*)?supporting\s+information\b', 'Supporting Information', 0.85),
        (r'^(?:\d+\.?\s*)?supplementary\b', 'Supplementary', 0.8),
        # Review-specific
        (r'^(?:\d+\.?\s*)?literature\s+review\b', 'Literature Review', 0.85),
        (r'^(?:\d+\.?\s*)?related\s+work\b', 'Related Work', 0.85),
        (r'^(?:\d+\.?\s*)?theoretical\s+(?:framework|background)\b', 'Theory', 0.8),
        # Numbered sections (generic)
        (r'^(\d+)\.\s+[A-Z][A-Za-z\s]+$', 'Numbered Section', 0.6),
    ]

    @staticmethod
    def get_structure_hints(text: str) -> DocumentStructure:
        """Perform quick heuristic scan for document structure.

        This is a fallible initial scan - the LLM should validate/correct.
        Returns detected sections with confidence levels.
        """
        structure = DocumentStructure()
        structure.estimated_word_count = len(text.split())

        # Check for abstract
        if re.search(r'\babstract\b', text[:5000], re.IGNORECASE):
            structure.has_abstract = True

        # Check for references section
        if re.search(r'\breferences?\b|\bbibliography\b', text[-10000:], re.IGNORECASE):
            structure.has_references = True

        # Scan for section headers
        lines = text.split('\n')
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) > 100:
                continue

            for pattern, section_name, confidence in ExtractionService.SECTION_PATTERNS:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    # Calculate character position
                    char_pos = sum(len(line) + 1 for line in lines[:i])
                    structure.sections.append(SectionHint(
                        name=section_name,
                        start_position=char_pos,
                        confidence=confidence,
                        matched_pattern=pattern
                    ))
                    break  # Only match first pattern per line

        # Detect document type from structure
        section_names = {s.name.lower() for s in structure.sections}

        if 'methods' in section_names and 'results' in section_names:
            structure.detected_type = 'research_article'
            structure.type_confidence = 0.8
        elif 'literature review' in section_names or len(structure.sections) > 10:
            structure.detected_type = 'review'
            structure.type_confidence = 0.6
        elif structure.estimated_word_count < 4000:
            structure.detected_type = 'short_communication'
            structure.type_confidence = 0.5
        elif structure.has_abstract and structure.has_references:
            structure.detected_type = 'research_article'
            structure.type_confidence = 0.5

        return structure

    @staticmethod
    def _split_into_chunks(
        text: str,
        target_words: int,
        structure: DocumentStructure | None = None
    ) -> list[str]:
        """Split text into chunks, preferring section boundaries.

        Args:
            text: Full text to split
            target_words: Target words per chunk
            structure: Optional document structure hints for section-aware splitting

        Returns:
            List of text chunks
        """
        if not text.strip():
            return []

        # If no structure hints or few sections, use simple paragraph-based splitting
        if not structure or len(structure.sections) < 2:
            return ExtractionService._split_by_paragraphs(text, target_words)

        # Section-aware splitting
        chunks = []
        section_positions = sorted(
            [(s.start_position, s.name) for s in structure.sections],
            key=lambda x: x[0]
        )

        # Add end position
        section_positions.append((len(text), "END"))

        for i in range(len(section_positions) - 1):
            start_pos = section_positions[i][0]
            end_pos = section_positions[i + 1][0]
            section_name = section_positions[i][1]
            section_text = text[start_pos:end_pos].strip()

            if not section_text:
                continue

            section_words = len(section_text.split())

            # If section fits in one chunk, keep it together
            if section_words <= target_words * 1.2:  # Allow 20% overage to keep sections intact
                # Add section marker for LLM context
                chunks.append(f"[Section: {section_name}]\n\n{section_text}")
            else:
                # Split large sections by paragraphs
                sub_chunks = ExtractionService._split_by_paragraphs(section_text, target_words)
                for j, sub_chunk in enumerate(sub_chunks):
                    part_marker = f" (part {j+1}/{len(sub_chunks)})" if len(sub_chunks) > 1 else ""
                    chunks.append(f"[Section: {section_name}{part_marker}]\n\n{sub_chunk}")

        return chunks if chunks else ExtractionService._split_by_paragraphs(text, target_words)

    @staticmethod
    def _split_by_paragraphs(text: str, target_words: int) -> list[str]:
        """Simple paragraph-based splitting (original algorithm)."""
        paragraphs = re.split(r'\n\s*\n', text)

        chunks = []
        current_chunk = []
        current_words = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_words = len(para.split())

            if current_words + para_words > target_words and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_words = para_words
            else:
                current_chunk.append(para)
                current_words += para_words

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    @staticmethod
    def _clear_pdf_extraction(session, paper_id: int) -> None:
        """Clear existing PDF extraction data for a paper."""
        session.query(PaperChunk).filter(PaperChunk.paper_id == paper_id).delete()
        session.query(PaperTable).filter(PaperTable.paper_id == paper_id).delete()
        session.query(PaperFigure).filter(PaperFigure.paper_id == paper_id).delete()
        session.query(PaperReference).filter(PaperReference.paper_id == paper_id).delete()

    @staticmethod
    def get_pdf_extraction_status(paper_id: int) -> dict | None:
        """Get PDF extraction status for a paper.

        Returns:
            Dict with extraction info, or None if not extracted
        """
        with get_session() as session:
            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            if not metadata:
                return None

            return {
                "paper_id": paper_id,
                "method": metadata.extraction_method,
                "chunk_count": metadata.chunk_count or 0,
                "table_count": metadata.table_count or 0,
                "figure_count": metadata.figure_count or 0,
                "word_count": metadata.word_count or 0,
                "page_count": metadata.page_count or 0,
                "extraction_date": metadata.extraction_date.isoformat() if metadata.extraction_date else None,
            }

    @staticmethod
    def get_chunk(paper_id: int, chunk_num: int) -> dict | None:
        """Get a specific chunk by number.

        Args:
            paper_id: Paper ID
            chunk_num: Chunk number (0-indexed)

        Returns:
            Dict with chunk info, or None if not found
        """
        with get_session() as session:
            chunk = session.query(PaperChunk).filter(
                PaperChunk.paper_id == paper_id,
                PaperChunk.chunk_order == chunk_num,
            ).first()

            if not chunk:
                return None

            # Get total chunks for context
            total = session.query(PaperChunk).filter(
                PaperChunk.paper_id == paper_id
            ).count()

            return {
                "chunk_num": chunk_num,
                "total_chunks": total,
                "content": chunk.content,
                "word_count": chunk.word_count,
                "char_count": chunk.char_count,
            }

    @staticmethod
    def get_all_chunks(paper_id: int) -> list[dict]:
        """Get all chunks for a paper.

        Returns:
            List of chunk dicts ordered by chunk_order
        """
        with get_session() as session:
            chunks = session.query(PaperChunk).filter(
                PaperChunk.paper_id == paper_id
            ).order_by(PaperChunk.chunk_order).all()

            return [{
                "chunk_num": c.chunk_order,
                "content": c.content,
                "word_count": c.word_count,
                "char_count": c.char_count,
            } for c in chunks]

    @staticmethod
    def get_tables(paper_id: int) -> list[dict]:
        """Get all tables for a paper."""
        with get_session() as session:
            tables = session.query(PaperTable).filter(
                PaperTable.paper_id == paper_id
            ).order_by(PaperTable.table_order).all()

            return [{
                "table_num": t.table_order,
                "markdown": t.markdown,
                "caption": t.caption,
                "row_count": t.row_count,
                "col_count": t.col_count,
                "page": t.page_number,
            } for t in tables]

    @staticmethod
    def get_figures(paper_id: int) -> list[dict]:
        """Get all figure/table captions for a paper."""
        with get_session() as session:
            figures = session.query(PaperFigure).filter(
                PaperFigure.paper_id == paper_id
            ).all()

            return [{
                "type": f.figure_type,
                "number": f.figure_number,
                "caption": f.caption,
                "page": f.page_number,
            } for f in figures]

    @staticmethod
    def prepare_for_claude(
        paper_id: int,
        chunk_num: int | None = None,
        include_tables: bool = True,
        include_figures: bool = True,
    ) -> str:
        """Format extraction for Claude processing.

        Args:
            paper_id: Paper ID
            chunk_num: Specific chunk to include (None = all chunks)
            include_tables: Include extracted tables
            include_figures: Include figure captions

        Returns:
            Formatted content for Claude
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return f"Error: Paper {paper_id} not found"

            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            if not metadata:
                return f"Error: Paper {paper_id} not extracted. Run extract_pdf_and_store first."

            parts = []

            # Header
            parts.append(f"# {paper.title}")
            if paper.authors:
                author_names = ", ".join(a.name for a in paper.authors)
                parts.append(f"Authors: {author_names}")
            if paper.year:
                parts.append(f"Year: {paper.year}")
            parts.append("")

            # Extraction info
            parts.append(
                f"[{metadata.word_count:,} words | {metadata.page_count} pages | "
                f"{metadata.chunk_count} chunks]"
            )
            parts.append("")

            # Get chunks
            if chunk_num is not None:
                chunks = session.query(PaperChunk).filter(
                    PaperChunk.paper_id == paper_id,
                    PaperChunk.chunk_order == chunk_num,
                ).all()
                parts.append(f"## Chunk {chunk_num + 1} of {metadata.chunk_count}")
            else:
                chunks = session.query(PaperChunk).filter(
                    PaperChunk.paper_id == paper_id
                ).order_by(PaperChunk.chunk_order).all()
                parts.append("## Full Text")

            parts.append("")
            for chunk in chunks:
                parts.append(chunk.content)
                parts.append("")

            # Tables
            if include_tables and metadata.table_count and metadata.table_count > 0:
                tables = session.query(PaperTable).filter(
                    PaperTable.paper_id == paper_id
                ).order_by(PaperTable.table_order).all()

                parts.append("---")
                parts.append(f"## Extracted Tables ({len(tables)})")
                parts.append("")
                for i, table in enumerate(tables, 1):
                    parts.append(f"### Table {i}" + (f" (Page {table.page_number})" if table.page_number else ""))
                    if table.caption:
                        parts.append(f"*{table.caption}*")
                    parts.append("")
                    parts.append(table.markdown)
                    parts.append("")

            # Figures
            if include_figures:
                figures = session.query(PaperFigure).filter(
                    PaperFigure.paper_id == paper_id
                ).all()

                if figures:
                    parts.append("---")
                    parts.append(f"## Figure/Table Captions ({len(figures)})")
                    parts.append("")
                    for fig in figures:
                        parts.append(f"**{fig.figure_type.title()} {fig.figure_number}:** {fig.caption}")
                    parts.append("")

            return "\n".join(parts)

    @staticmethod
    def needs_pdf_extraction(paper_id: int) -> bool:
        """Check if a paper needs PDF extraction."""
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper or not paper.file_path:
                return False

            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            return metadata is None or metadata.needs_reextraction == 1

    @staticmethod
    def get_papers_needing_pdf_extraction(limit: int = 50) -> list[int]:
        """Get paper IDs that need PDF extraction."""
        with get_session() as session:
            # Papers with PDFs but no extraction
            papers = session.query(Paper.id).filter(
                Paper.file_path.isnot(None),
                ~Paper.id.in_(
                    session.query(ExtractionMetadata.paper_id)
                )
            ).limit(limit).all()

            return [p.id for p in papers]

    # =========================================================================
    # Queue Management Methods (from ChunkingQueueService)
    # =========================================================================

    @staticmethod
    def queue_extraction(
        paper_id: int,
        force: bool = False,
    ) -> dict:
        """Queue a paper for PDF extraction.

        Args:
            paper_id: Paper ID to queue
            force: Queue even if already extracted

        Returns:
            Dict with queue status
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return {
                    "status": "error",
                    "error": f"Paper {paper_id} not found",
                }

            if not paper.file_path:
                return {
                    "status": "error",
                    "error": "Paper has no PDF attached",
                }

            # Get or create extraction metadata
            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            if metadata:
                # Check if already chunked (only skip if actually has chunks)
                if (metadata.chunking_status == ChunkingStatus.COMPLETE
                        and (metadata.chunk_count or 0) > 0
                        and not force):
                    return {
                        "status": "already_complete",
                        "chunk_count": metadata.chunk_count or 0,
                    }

                # Check if already processing
                if metadata.chunking_status == ChunkingStatus.PROCESSING:
                    return {
                        "status": "already_processing",
                    }

                # Update status to pending
                metadata.chunking_status = ChunkingStatus.PENDING
                metadata.chunking_queued_at = datetime.utcnow()
                metadata.chunking_error = None
            else:
                # Create new metadata record
                metadata = ExtractionMetadata(
                    paper_id=paper_id,
                    chunking_status=ChunkingStatus.PENDING,
                    chunking_queued_at=datetime.utcnow(),
                )
                session.add(metadata)

            # Update paper enrichment status if needed
            if paper.enrichment_status in (EnrichmentStatus.NEEDS_PDF, EnrichmentStatus.PENDING):
                paper.enrichment_status = EnrichmentStatus.NEEDS_CHUNKING

            return {
                "status": "queued",
                "paper_id": paper_id,
            }

    @classmethod
    def process_extraction_single(
        cls,
        paper_id: int,
        force: bool = False,
        progress_callback: ProgressCallback | None = None,
    ) -> ChunkingResult:
        """Process PDF extraction for a single paper immediately.

        Args:
            paper_id: Paper ID to process
            force: Re-extract even if already done
            progress_callback: Optional callback for progress updates

        Returns:
            ChunkingResult with outcome
        """
        with get_session() as session:
            paper = session.query(Paper).filter(Paper.id == paper_id).first()
            if not paper:
                return ChunkingResult(
                    paper_id=paper_id,
                    status="failed",
                    error=f"Paper {paper_id} not found",
                )

            if not paper.file_path:
                return ChunkingResult(
                    paper_id=paper_id,
                    status="skipped",
                    error="No PDF attached",
                )

            # Get or create metadata
            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            if not metadata:
                metadata = ExtractionMetadata(paper_id=paper_id)
                session.add(metadata)
                session.flush()

            # Update status to processing
            metadata.chunking_status = ChunkingStatus.PROCESSING
            session.commit()

        # Do the extraction (outside transaction to avoid long locks)
        try:
            result = cls.extract_pdf_and_store(
                paper_id=paper_id,
                force=force,
                progress_callback=progress_callback,
            )
        except Exception as e:
            logger.error(f"Extraction failed for paper {paper_id}: {e}")
            with get_session() as session:
                metadata = session.query(ExtractionMetadata).filter(
                    ExtractionMetadata.paper_id == paper_id
                ).first()
                if metadata:
                    metadata.chunking_status = ChunkingStatus.FAILED
                    metadata.chunking_error = str(e)

            return ChunkingResult(
                paper_id=paper_id,
                status="failed",
                error=str(e),
            )

        # Update status based on result
        with get_session() as session:
            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            paper = session.query(Paper).filter(Paper.id == paper_id).first()

            if result.success:
                if metadata:
                    metadata.chunking_status = ChunkingStatus.COMPLETE
                    metadata.chunking_error = None

                # Update paper enrichment status - ready for AI extraction
                if paper:
                    paper.enrichment_status = EnrichmentStatus.NEEDS_EXTRACTION

                return ChunkingResult(
                    paper_id=paper_id,
                    status="complete",
                    chunk_count=result.chunk_count,
                )
            else:
                if metadata:
                    metadata.chunking_status = ChunkingStatus.FAILED
                    metadata.chunking_error = result.error

                # Update paper enrichment status
                if paper:
                    paper.enrichment_status = EnrichmentStatus.FAILED

                return ChunkingResult(
                    paper_id=paper_id,
                    status="failed",
                    error=result.error,
                )

    @classmethod
    def process_extraction_queue(
        cls,
        limit: int = 10,
        force: bool = False,
    ) -> list[ChunkingResult]:
        """Process papers in the extraction queue.

        Args:
            limit: Maximum papers to process
            force: Re-extract even if chunks exist

        Returns:
            List of ChunkingResult for each processed paper
        """
        # Get pending papers
        with get_session() as session:
            pending = session.query(ExtractionMetadata.paper_id).filter(
                ExtractionMetadata.chunking_status == ChunkingStatus.PENDING
            ).order_by(ExtractionMetadata.chunking_queued_at).limit(limit).all()

            paper_ids = [p.paper_id for p in pending]

        results = []
        for paper_id in paper_ids:
            result = cls.process_extraction_single(paper_id, force=force)
            results.append(result)
            logger.info(
                f"Processed extraction for paper {paper_id}: {result.status}",
                extra={"paper_id": paper_id, "status": result.status}
            )

        return results

    @staticmethod
    def get_queue_status(paper_id: int) -> dict:
        """Get extraction queue status for a paper.

        Returns:
            Dict with status info
        """
        with get_session() as session:
            metadata = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.paper_id == paper_id
            ).first()

            if not metadata:
                paper = session.query(Paper).filter(Paper.id == paper_id).first()
                if not paper:
                    return {"status": "not_found", "error": "Paper not found"}
                if not paper.file_path:
                    return {"status": "no_pdf", "error": "Paper has no PDF"}
                return {"status": "not_extracted"}

            return {
                "status": metadata.chunking_status or "none",
                "chunk_count": metadata.chunk_count or 0,
                "queued_at": metadata.chunking_queued_at.isoformat() if metadata.chunking_queued_at else None,
                "error": metadata.chunking_error,
            }

    @staticmethod
    def get_extraction_queue(
        status: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get papers in the extraction queue.

        Args:
            status: Filter by status (pending, processing, failed)
            limit: Maximum papers to return

        Returns:
            List of papers with their extraction status
        """
        with get_session() as session:
            query = session.query(
                Paper.id,
                Paper.title,
                Paper.file_path,
                ExtractionMetadata.chunking_status,
                ExtractionMetadata.chunking_queued_at,
                ExtractionMetadata.chunking_error,
                ExtractionMetadata.chunk_count,
            ).outerjoin(
                ExtractionMetadata, Paper.id == ExtractionMetadata.paper_id
            ).filter(
                Paper.file_path.isnot(None)
            )

            if status:
                if status == "pending":
                    query = query.filter(
                        ExtractionMetadata.chunking_status == ChunkingStatus.PENDING
                    )
                elif status == "processing":
                    query = query.filter(
                        ExtractionMetadata.chunking_status == ChunkingStatus.PROCESSING
                    )
                elif status == "failed":
                    query = query.filter(
                        ExtractionMetadata.chunking_status == ChunkingStatus.FAILED
                    )
                elif status == "needs_extraction":
                    # Papers with PDF but no chunks (never processed, or completed with 0 chunks)
                    query = query.filter(
                        (ExtractionMetadata.chunking_status.is_(None)) |
                        (ExtractionMetadata.chunking_status == ChunkingStatus.NONE) |
                        (
                            (ExtractionMetadata.chunking_status == ChunkingStatus.COMPLETE) &
                            ((ExtractionMetadata.chunk_count.is_(None)) | (ExtractionMetadata.chunk_count == 0))
                        )
                    )

            query = query.order_by(ExtractionMetadata.chunking_queued_at.desc().nullslast())
            results = query.limit(limit).all()

            return [{
                "paper_id": r.id,
                "title": r.title,
                "has_pdf": bool(r.file_path),
                "chunking_status": r.chunking_status or "none",
                "queued_at": r.chunking_queued_at.isoformat() if r.chunking_queued_at else None,
                "error": r.chunking_error,
                "chunk_count": r.chunk_count or 0,
            } for r in results]

    @staticmethod
    def get_queue_stats() -> QueueStats:
        """Get statistics about the extraction queue.

        Returns:
            QueueStats with counts by status
        """
        with get_session() as session:
            # Count papers with PDFs
            total_with_pdf = session.query(func.count(Paper.id)).filter(
                Paper.file_path.isnot(None)
            ).scalar() or 0

            # Count by chunking status
            status_counts = session.query(
                ExtractionMetadata.chunking_status,
                func.count(ExtractionMetadata.paper_id)
            ).group_by(ExtractionMetadata.chunking_status).all()

            counts = {s: c for s, c in status_counts}

            return QueueStats(
                pending=counts.get(ChunkingStatus.PENDING, 0),
                processing=counts.get(ChunkingStatus.PROCESSING, 0),
                complete=counts.get(ChunkingStatus.COMPLETE, 0),
                failed=counts.get(ChunkingStatus.FAILED, 0),
                none=counts.get(ChunkingStatus.NONE, 0) + counts.get(None, 0),
                total_with_pdf=total_with_pdf,
            )

    @staticmethod
    def retry_failed_extractions(limit: int = 10) -> list[dict]:
        """Re-queue failed extraction attempts.

        Args:
            limit: Maximum papers to re-queue

        Returns:
            List of re-queued papers
        """
        with get_session() as session:
            failed = session.query(ExtractionMetadata).filter(
                ExtractionMetadata.chunking_status == ChunkingStatus.FAILED
            ).limit(limit).all()

            requeued = []
            for metadata in failed:
                metadata.chunking_status = ChunkingStatus.PENDING
                metadata.chunking_queued_at = datetime.utcnow()
                metadata.chunking_error = None
                requeued.append({
                    "paper_id": metadata.paper_id,
                    "status": "requeued",
                })

            return requeued

    @classmethod
    def queue_papers_needing_extraction(cls, limit: int = 50) -> list[dict]:
        """Find and queue papers with PDFs that need extraction.

        Args:
            limit: Maximum papers to queue

        Returns:
            List of queued papers
        """
        with get_session() as session:
            # Find papers with PDFs but no extraction metadata or chunking_status='none'
            papers_no_metadata = session.query(Paper.id).filter(
                Paper.file_path.isnot(None),
                ~Paper.id.in_(
                    session.query(ExtractionMetadata.paper_id)
                )
            ).limit(limit).all()

            papers_not_chunked = session.query(Paper.id).join(
                ExtractionMetadata, Paper.id == ExtractionMetadata.paper_id
            ).filter(
                Paper.file_path.isnot(None),
                (ExtractionMetadata.chunking_status.is_(None)) |
                (ExtractionMetadata.chunking_status == ChunkingStatus.NONE)
            ).limit(limit - len(papers_no_metadata)).all()

            paper_ids = [p.id for p in papers_no_metadata] + [p.id for p in papers_not_chunked]

        queued = []
        for paper_id in paper_ids[:limit]:
            result = cls.queue_extraction(paper_id)
            queued.append({
                "paper_id": paper_id,
                **result,
            })

        return queued

    # =========================================================================
    # Quality Checking Methods
    # =========================================================================

    @classmethod
    def check_quality(cls, paper_id: int) -> QualityReport:
        """Check extraction quality for a single paper.

        Performs various quality checks on the extraction and returns a report
        with issues and warnings.

        Args:
            paper_id: Paper ID to check

        Returns:
            QualityReport with issues, warnings, and score
        """
        with get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper:
                return QualityReport(
                    paper_id=paper_id,
                    paper_title="Unknown",
                    issues=["Paper not found"],
                    score=0.0
                )

            content = session.query(PaperContent).filter(
                PaperContent.paper_id == paper_id
            ).first()

            report = QualityReport(
                paper_id=paper_id,
                paper_title=paper.title or "Untitled"
            )

            # No extraction at all
            if not content:
                report.issues.append("No extraction content found")
                report.score = 0.0
                return report

            # Check summary length
            summary = content.one_sentence_summary or ""
            has_full_text = paper.word_count and paper.word_count > 500
            if has_full_text and len(summary) < 50:
                report.issues.append(f"Summary too short ({len(summary)} chars) for paper with full text")

            # Check key findings count
            key_findings = content.key_findings or []
            paper_type = content.paper_type or ""
            if paper_type == "research_article" and len(key_findings) < 3:
                report.warnings.append(f"Only {len(key_findings)} key findings for research article (expected >= 3)")

            # Check methodology for experimental papers
            methodology = content.methodology_summary or ""
            if paper_type == "research_article" and len(methodology) < 50:
                report.warnings.append("Methodology summary missing or too brief for research article")

            # Check paper type consistency with word count
            word_count = paper.word_count or 0
            if paper_type == "review" and word_count < 5000:
                report.warnings.append(f"Paper type is 'review' but only {word_count} words (reviews typically > 5000)")

            # Check for quantitative results when abstract mentions numbers
            abstract = paper.abstract or ""
            has_numbers_in_abstract = bool(re.search(r'\d+\.?\d*\s*[%°CKÅnm]', abstract))
            structured_data = content.structured_data or {}
            quant_results = structured_data.get("quantitative_results", [])
            if has_numbers_in_abstract and not quant_results:
                report.warnings.append("Abstract contains numbers but no quantitative results extracted")

            # Check topics relevance (simple heuristic)
            topics = content.topics or []
            title_words = set(paper.title.lower().split()) if paper.title else set()
            if topics and title_words:
                topic_words = set(" ".join(topics).lower().split())
                overlap = title_words & topic_words
                if len(overlap) == 0 and len(title_words) > 3:
                    report.warnings.append("No overlap between topics and title words")

            # Calculate score based on issues and warnings
            issue_penalty = 0.3 * len(report.issues)
            warning_penalty = 0.1 * len(report.warnings)
            report.score = max(0.0, 1.0 - issue_penalty - warning_penalty)

            return report

    @classmethod
    def batch_quality_check(cls, limit: int = 50) -> list[QualityReport]:
        """Check extraction quality for multiple papers.

        Args:
            limit: Maximum papers to check

        Returns:
            List of QualityReport objects, sorted by score (lowest first)
        """
        with get_session() as session:
            # Get papers with extractions
            paper_ids = session.query(PaperContent.paper_id).limit(limit).all()
            paper_ids = [pid for (pid,) in paper_ids]

        reports = []
        for paper_id in paper_ids:
            report = cls.check_quality(paper_id)
            reports.append(report)

        # Sort by score (lowest first = most issues)
        reports.sort(key=lambda r: r.score)
        return reports

    @classmethod
    def generate_quality_report(cls, limit: int = 50) -> str:
        """Generate a markdown quality report for extractions.

        Args:
            limit: Maximum papers to check

        Returns:
            Markdown-formatted report string
        """
        reports = cls.batch_quality_check(limit)

        # Count statistics
        total = len(reports)
        with_issues = sum(1 for r in reports if r.has_issues)
        needs_review = sum(1 for r in reports if r.needs_review)
        avg_score = sum(r.score for r in reports) / total if total > 0 else 0

        lines = [
            "# Extraction Quality Report",
            "",
            "## Summary",
            f"- **Papers checked:** {total}",
            f"- **Papers with issues:** {with_issues}",
            f"- **Papers needing review (score < 0.7):** {needs_review}",
            f"- **Average quality score:** {avg_score:.2f}",
            "",
        ]

        # Flagged papers (score < 0.7)
        flagged = [r for r in reports if r.needs_review]
        if flagged:
            lines.append("## Flagged Papers (Need Review)")
            lines.append("")
            for report in flagged[:20]:  # Limit to top 20
                lines.append(f"### Paper {report.paper_id}: {report.paper_title[:60]}")
                lines.append(f"**Score:** {report.score:.2f}")
                if report.issues:
                    lines.append("**Issues:**")
                    for issue in report.issues:
                        lines.append(f"  - {issue}")
                if report.warnings:
                    lines.append("**Warnings:**")
                    for warning in report.warnings:
                        lines.append(f"  - {warning}")
                lines.append("")

        # Papers with warnings only
        warned = [r for r in reports if not r.has_issues and r.warnings]
        if warned:
            lines.append("## Papers with Warnings")
            lines.append("")
            for report in warned[:10]:  # Limit to top 10
                lines.append(f"- **Paper {report.paper_id}** ({report.score:.2f}): {', '.join(report.warnings[:2])}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def verify_extraction(cls, paper_id: int) -> dict:
        """Verify extracted data against source text.

        Checks if extracted claims, findings, and quantitative results
        can be found in the source text (chunks or abstract).

        Args:
            paper_id: Paper ID to verify

        Returns:
            Dict with verification results including:
            - verified_claims: Claims found in source
            - unverified_claims: Claims not found (potential hallucinations)
            - source_excerpts: Relevant source text snippets
        """
        with get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper:
                return {"error": f"Paper {paper_id} not found"}

            content = session.query(PaperContent).filter(
                PaperContent.paper_id == paper_id
            ).first()

            if not content:
                return {"error": f"No extraction found for paper {paper_id}"}

            # Get source text
            chunks = cls.get_all_chunks(paper_id)
            source_text = " ".join(c["content"] for c in chunks) if chunks else ""
            if not source_text:
                source_text = paper.abstract or ""

            source_lower = source_text.lower()

            # Verify key findings
            key_findings = content.key_findings or []
            verified_findings = []
            unverified_findings = []

            for finding in key_findings:
                # Extract key terms from finding (numbers, technical terms)
                evidence = cls._find_evidence(finding, source_text, source_lower)
                if evidence["found"]:
                    verified_findings.append({
                        "claim": finding,
                        "evidence": evidence["excerpt"],
                        "confidence": evidence["confidence"]
                    })
                else:
                    unverified_findings.append({
                        "claim": finding,
                        "reason": evidence["reason"]
                    })

            # Verify citable claims
            structured_data = content.structured_data or {}
            citable_claims = structured_data.get("citable_claims", [])
            verified_claims = []
            unverified_claims = []

            for claim in citable_claims:
                evidence = cls._find_evidence(claim, source_text, source_lower)
                if evidence["found"]:
                    verified_claims.append({
                        "claim": claim,
                        "evidence": evidence["excerpt"],
                        "confidence": evidence["confidence"]
                    })
                else:
                    unverified_claims.append({
                        "claim": claim,
                        "reason": evidence["reason"]
                    })

            # Verify quantitative results
            quant_results = structured_data.get("quantitative_results", [])
            verified_quant = []
            unverified_quant = []

            for result in quant_results:
                if isinstance(result, dict):
                    value = str(result.get("value", ""))

                    # Search for the numeric value in source
                    found = value in source_text
                    if found:
                        # Get context around the value
                        idx = source_text.find(value)
                        start = max(0, idx - 100)
                        end = min(len(source_text), idx + len(value) + 100)
                        excerpt = source_text[start:end]
                        verified_quant.append({
                            "result": result,
                            "evidence": f"...{excerpt}..."
                        })
                    else:
                        unverified_quant.append({
                            "result": result,
                            "reason": f"Value '{value}' not found in source text"
                        })

            # Check for cited_references (flag as unreliable)
            cited_refs = structured_data.get("cited_references", [])
            cited_refs_warning = None
            if cited_refs:
                cited_refs_warning = (
                    "cited_references field is UNRELIABLE - LLM may hallucinate "
                    "claim-to-reference mappings. These should not be trusted."
                )

            # Calculate verification score
            total_items = len(key_findings) + len(citable_claims) + len(quant_results)
            verified_items = len(verified_findings) + len(verified_claims) + len(verified_quant)
            verification_score = verified_items / total_items if total_items > 0 else 1.0

            return {
                "paper_id": paper_id,
                "paper_title": paper.title,
                "verification_score": round(verification_score, 2),
                "source_text_available": bool(source_text),
                "source_word_count": len(source_text.split()),
                "key_findings": {
                    "verified": verified_findings,
                    "unverified": unverified_findings,
                    "total": len(key_findings)
                },
                "citable_claims": {
                    "verified": verified_claims,
                    "unverified": unverified_claims,
                    "total": len(citable_claims)
                },
                "quantitative_results": {
                    "verified": verified_quant,
                    "unverified": unverified_quant,
                    "total": len(quant_results)
                },
                "cited_references_warning": cited_refs_warning,
                "recommendation": cls._get_verification_recommendation(verification_score)
            }

    @staticmethod
    def _find_evidence(claim: str, source_text: str, source_lower: str) -> dict:
        """Find evidence for a claim in source text.

        Uses multiple strategies:
        1. Look for numeric values mentioned in the claim
        2. Look for key technical terms
        3. Look for partial phrase matches

        Returns:
            Dict with 'found', 'excerpt', 'confidence', 'reason'
        """
        # Extract numbers from claim
        numbers = re.findall(r'\d+\.?\d*', claim)
        claim_lower = claim.lower()

        # Strategy 1: Find exact numbers
        for num in numbers:
            if num in source_text:
                idx = source_text.find(num)
                start = max(0, idx - 80)
                end = min(len(source_text), idx + len(num) + 80)
                excerpt = source_text[start:end]
                return {
                    "found": True,
                    "excerpt": f"...{excerpt}...",
                    "confidence": "high" if len(numbers) <= 2 else "medium",
                    "reason": None
                }

        # Strategy 2: Look for key terms (3+ char words, excluding common words)
        common_words = {
            "the", "and", "for", "was", "were", "with", "this", "that",
            "from", "have", "been", "are", "can", "has", "had", "not",
            "but", "which", "their", "they", "these", "those", "than"
        }
        words = re.findall(r'\b[a-zA-Z]{3,}\b', claim_lower)
        key_terms = [w for w in words if w not in common_words]

        # Find sentences containing key terms
        sentences = source_text.split('.')
        for sentence in sentences:
            sentence_lower = sentence.lower()
            matching_terms = sum(1 for term in key_terms[:5] if term in sentence_lower)
            if matching_terms >= 3:  # At least 3 key terms match
                return {
                    "found": True,
                    "excerpt": sentence.strip()[:200] + "...",
                    "confidence": "medium",
                    "reason": None
                }

        # Strategy 3: Partial phrase match (consecutive words)
        words_in_claim = claim_lower.split()
        for i in range(len(words_in_claim) - 2):
            phrase = " ".join(words_in_claim[i:i+3])
            if phrase in source_lower and len(phrase) > 10:
                idx = source_lower.find(phrase)
                start = max(0, idx - 50)
                end = min(len(source_text), idx + len(phrase) + 50)
                excerpt = source_text[start:end]
                return {
                    "found": True,
                    "excerpt": f"...{excerpt}...",
                    "confidence": "low",
                    "reason": None
                }

        return {
            "found": False,
            "excerpt": None,
            "confidence": None,
            "reason": "No matching content found in source text"
        }

    @staticmethod
    def _get_verification_recommendation(score: float) -> str:
        """Get recommendation based on verification score."""
        if score >= 0.8:
            return "Extraction appears well-grounded in source text"
        elif score >= 0.5:
            return "Some claims unverified - manual review recommended"
        elif score > 0:
            return "Many claims unverified - likely contains hallucinations, re-extraction suggested"
        else:
            return "Unable to verify - no extractable claims or missing source text"

    @classmethod
    def batch_verify(cls, paper_ids: list[int] | None = None, limit: int = 20) -> list[dict]:
        """Verify extractions for multiple papers.

        Args:
            paper_ids: Specific paper IDs to verify (or None for all with extractions)
            limit: Maximum papers to verify

        Returns:
            List of verification results sorted by score (lowest first)
        """
        if paper_ids is None:
            # Get papers with extractions
            papers = cls.get_papers_with_extractions(limit=limit)
            paper_ids = [p["id"] for p in papers]

        results = []
        for pid in paper_ids[:limit]:
            try:
                result = cls.verify_extraction(pid)
                if "error" not in result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to verify paper {pid}: {e}")

        # Sort by verification score (lowest first - most problematic)
        results.sort(key=lambda x: x.get("verification_score", 1.0))
        return results
