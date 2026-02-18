"""Multi-Pass Extraction Script for Ollama.

Follows the same workflow as Claude extraction:
1. Read paper in chunks (20K chars each)
2. Save intermediate notes to database after each chunk
3. Consolidate all notes into final extraction
4. Clean up temp notes

This protects against crashes/timeouts - progress is saved per-chunk.

Relevance-based filtering:
- High/Medium relevance → Full multi-pass extraction
- Low/None relevance AND >10 chunks → Quick abstract-only (skip full text)
- Low/None relevance AND ≤10 chunks → Full multi-pass (short papers anyway)

Run with:
    cd /home/dreece23/projects/research/misc/research
    /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.multipass_extraction

Options:
    --paper-id N     Extract specific paper
    --batch N        Extract N papers from queue
    --dry-run        Show what would be done
    --continue       Resume from saved notes
    --no-filter      Ignore relevance filter, extract all papers fully
"""
from __future__ import annotations

import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import httpx
from sqlalchemy import text
from literature_core import get_session, get_logger, Paper, PaperChunk, PaperContent
from services.paper_service import PaperService
from config.ai_settings import settings

logger = get_logger(__name__)

# Constants
CHUNK_SIZE = 20000  # chars per chunk
OLLAMA_TIMEOUT = 300  # seconds
LONG_PAPER_THRESHOLD = 10  # chunks - papers above this with low relevance get quick extract only

# Project topics for relevance scoring (from data/projects.json)
PROJECT_TOPICS = {
    "thesis": [
        "molecular layer deposition", "mld", "atomic layer deposition", "ald",
        "thin films", "euv lithography", "extreme ultraviolet", "tincones",
        "alucones", "zincones", "hybrid organic-inorganic", "reactor design",
        "high-throughput screening", "combinatorial synthesis", "photoresist"
    ],
    "paper2": [
        "euv photoresist", "extreme ultraviolet lithography", "alucones", "zincones",
        "mld resist", "photoresist stability", "outgassing", "pattern transfer",
        "dose sensitivity", "line-edge roughness", "developer compatibility"
    ]
}


def score_relevance(title: str, abstract: str) -> tuple[str, list[str]]:
    """Score paper relevance to thesis/paper2 projects.

    Returns:
        (relevance_level, matched_topics)
        relevance_level: "high", "medium", "low", or "none"
    """
    text = f"{title} {abstract}".lower()
    matched = []

    # Check all topics
    for project, topics in PROJECT_TOPICS.items():
        for topic in topics:
            if topic in text:
                matched.append(f"{project}:{topic}")

    # Score based on matches
    unique_topics = len(set(t.split(":")[1] for t in matched))

    if unique_topics >= 3:
        return "high", matched
    elif unique_topics >= 1:
        return "medium", matched
    else:
        # Check for partial matches (single keywords)
        keywords = ["ald", "mld", "euv", "thin film", "deposition", "lithograph",
                    "photoresist", "resist", "alucone", "zincone", "tincone"]
        for kw in keywords:
            if kw in text:
                matched.append(f"keyword:{kw}")
        if matched:
            return "low", matched
        return "none", []


def should_full_extract(relevance: str, chunk_count: int) -> bool:
    """Determine if paper should get full multi-pass extraction.

    Returns True for:
    - High/Medium relevance papers (any length)
    - Low/None relevance papers with ≤10 chunks (short anyway)

    Returns False for:
    - Low/None relevance papers with >10 chunks (quick extract only)
    """
    if relevance in ("high", "medium"):
        return True
    return chunk_count <= LONG_PAPER_THRESHOLD


class MultiPassExtractor:
    """Multi-pass extraction using Ollama with note-saving."""

    def __init__(self, host: str = None, model: str = None):
        self.host = host or settings.ollama.host
        self.model = model or settings.ollama.reader_model

    async def extract_chunk(self, paper_id: int, chunk_num: int, chunk_text: str,
                           title: str, abstract: str) -> dict:
        """Extract findings from a single chunk.

        Returns dict with partial extraction for this chunk.
        """
        prompt = f"""You are analyzing CHUNK {chunk_num} of a research paper.

PAPER TITLE: {title}
ABSTRACT: {abstract}

CHUNK {chunk_num} CONTENT:
{chunk_text}

Extract key information from THIS CHUNK ONLY. Return JSON:
{{
    "chunk_number": {chunk_num},
    "section_type": "introduction|methods|results|discussion|conclusion|other",
    "key_points": ["point 1", "point 2", ...],
    "quantitative_data": [
        {{"metric": "...", "value": "...", "unit": "...", "context": "..."}}
    ],
    "techniques_mentioned": ["technique 1", "technique 2"],
    "citable_statements": ["quotable claim 1", "quotable claim 2"],
    "notes": "Any other important observations from this chunk"
}}

Respond ONLY with valid JSON."""

        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 1024,
                        }
                    }
                )

                if response.status_code != 200:
                    return {"error": f"Ollama error: {response.status_code}", "chunk_number": chunk_num}

                data = response.json()
                text = data.get("response", "")

                # Parse JSON
                text = text.strip()
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

                return json.loads(text)

        except Exception as e:
            logger.error(f"Chunk extraction error: {e}")
            return {"error": str(e), "chunk_number": chunk_num}

    async def consolidate_chunks(self, paper_id: int, title: str, abstract: str,
                                 chunk_notes: list[dict]) -> dict:
        """Consolidate all chunk notes into final extraction."""

        notes_text = "\n\n".join([
            f"=== CHUNK {n.get('chunk_number', i+1)} ({n.get('section_type', 'unknown')}) ===\n"
            f"Key points: {json.dumps(n.get('key_points', []))}\n"
            f"Quantitative: {json.dumps(n.get('quantitative_data', []))}\n"
            f"Techniques: {json.dumps(n.get('techniques_mentioned', []))}\n"
            f"Citable: {json.dumps(n.get('citable_statements', []))}\n"
            f"Notes: {n.get('notes', '')}"
            for i, n in enumerate(chunk_notes) if not n.get('error')
        ])

        prompt = f"""You are consolidating extraction notes from a multi-chunk paper analysis.

PAPER TITLE: {title}
ABSTRACT: {abstract}

CHUNK-BY-CHUNK NOTES:
{notes_text}

Consolidate ALL findings into a comprehensive extraction. Return JSON:
{{
    "paper_type": "research_article|review|conference|preprint|thesis|other",
    "topics": ["topic1", "topic2", "topic3", "topic4", "topic5"],
    "one_sentence_summary": "Comprehensive sentence: WHAT was done, HOW, and WHAT was the result",
    "key_findings": [
        "Finding 1 with specific numbers",
        "Finding 2 with data",
        "Finding 3",
        "Finding 4",
        "Finding 5"
    ],
    "quantitative_results": [
        {{"metric": "...", "value": "...", "unit": "...", "conditions": "..."}}
    ],
    "citable_claims": [
        "Specific quotable assertion 1",
        "Specific quotable assertion 2"
    ],
    "techniques_used": [
        {{"technique": "...", "purpose": "...", "specifics": "..."}}
    ],
    "methodology_summary": "4-6 sentence description of methods",
    "research_context": {{
        "problem_addressed": "...",
        "novelty": "...",
        "limitations": "...",
        "significance": "..."
    }},
    "future_directions": ["direction 1", "direction 2"]
}}

Combine and deduplicate information from all chunks. Be comprehensive.
Respond ONLY with valid JSON."""

        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 2048,
                        }
                    }
                )

                if response.status_code != 200:
                    return {"error": f"Ollama error: {response.status_code}"}

                data = response.json()
                text = data.get("response", "")

                # Parse JSON
                text = text.strip()
                if "```json" in text:
                    start = text.find("```json") + 7
                    end = text.find("```", start)
                    text = text[start:end].strip()

                brace_start = text.find("{")
                brace_end = text.rfind("}") + 1
                if brace_start >= 0 and brace_end > brace_start:
                    text = text[brace_start:brace_end]

                return json.loads(text)

        except Exception as e:
            logger.error(f"Consolidation error: {e}")
            return {"error": str(e)}

    async def quick_extract_abstract(self, paper_id: int, title: str, abstract: str) -> dict:
        """Quick extraction from abstract only - for long irrelevant papers.

        Returns basic categorization without full-text analysis.
        """
        prompt = f"""Analyze this research paper from its title and abstract ONLY.

TITLE: {title}

ABSTRACT: {abstract}

Extract basic categorization. Return JSON:
{{
    "paper_type": "research_article|review|conference|letter|preprint|thesis|other",
    "topics": ["topic1", "topic2", "topic3", "topic4", "topic5"],
    "one_sentence_summary": "Brief summary: WHAT was done, HOW, and RESULT",
    "key_findings": ["finding 1", "finding 2", "finding 3"],
    "methodology_summary": "Brief methods description from abstract"
}}

This is abstract-only extraction. Be concise.
Respond ONLY with valid JSON."""

        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 1024,
                        }
                    }
                )

                if response.status_code != 200:
                    return {"error": f"Ollama error: {response.status_code}"}

                data = response.json()
                text = data.get("response", "")

                # Parse JSON
                text = text.strip()
                if "```json" in text:
                    start = text.find("```json") + 7
                    end = text.find("```", start)
                    text = text[start:end].strip()

                brace_start = text.find("{")
                brace_end = text.rfind("}") + 1
                if brace_start >= 0 and brace_end > brace_start:
                    text = text[brace_start:brace_end]

                return json.loads(text)

        except Exception as e:
            logger.error(f"Quick extraction error: {e}")
            return {"error": str(e)}


def get_paper_chunks(paper_id: int) -> tuple[str, str, list[str]]:
    """Get paper metadata and full text split into chunks.

    Returns: (title, abstract, list_of_chunks)
    """
    with get_session() as session:
        paper = session.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            raise ValueError(f"Paper {paper_id} not found")

        title = paper.title or ""
        abstract = paper.abstract or ""

        # Get full text from chunks or legacy
        full_text = PaperService.get_full_text(paper_id, session) or paper.full_text

        if not full_text:
            return title, abstract, []

        # Split into chunks
        chunks = []
        for i in range(0, len(full_text), CHUNK_SIZE):
            chunk = full_text[i:i + CHUNK_SIZE]
            if chunk.strip():
                chunks.append(chunk)

        return title, abstract, chunks


def save_chunk_note(paper_id: int, chunk_num: int, content: dict) -> int:
    """Save chunk extraction as a note in database.

    Returns note ID.
    """
    from literature_core import Note

    with get_session() as session:
        note = Note(
            paper_id=paper_id,
            note_type="comment",
            content=f"MULTIPASS_CHUNK_{chunk_num}: {json.dumps(content)}",
            page_number=chunk_num,  # Abuse page_number to track chunk order
        )
        session.add(note)
        session.commit()
        return note.id


def get_saved_chunk_notes(paper_id: int) -> list[dict]:
    """Retrieve saved chunk notes for a paper."""
    from literature_core import Note

    with get_session() as session:
        notes = session.query(Note).filter(
            Note.paper_id == paper_id,
            Note.note_type == "comment",
            Note.content.like("MULTIPASS_CHUNK_%")
        ).order_by(Note.page_number).all()

        results = []
        for note in notes:
            try:
                # Parse content after the prefix
                content_start = note.content.find(": ") + 2
                content = json.loads(note.content[content_start:])
                results.append(content)
            except:
                pass

        return results


def delete_chunk_notes(paper_id: int) -> int:
    """Delete temporary chunk notes after successful extraction.

    Returns count deleted.
    """
    from literature_core import Note

    with get_session() as session:
        deleted = session.query(Note).filter(
            Note.paper_id == paper_id,
            Note.note_type == "comment",
            Note.content.like("MULTIPASS_CHUNK_%")
        ).delete(synchronize_session=False)
        session.commit()
        return deleted


def store_extraction(paper_id: int, extraction: dict, is_quick: bool = False) -> bool:
    """Store final consolidated extraction.

    Args:
        paper_id: Paper ID
        extraction: Extraction dict with paper_type, topics, etc.
        is_quick: If True, marks as quick/abstract-only extraction
    """
    model_name = f"ollama/quick/{settings.ollama.reader_model}" if is_quick else \
                 f"ollama/multipass/{settings.ollama.reader_model}"
    depth = "ABSTRACT_ONLY" if is_quick else "COMPREHENSIVE"

    with get_session() as session:
        # Build structured_data
        structured_data = {}
        for field in ["quantitative_results", "citable_claims", "techniques_used",
                      "research_context", "future_directions"]:
            if extraction.get(field):
                structured_data[field] = extraction[field]

        content = session.query(PaperContent).filter(
            PaperContent.paper_id == paper_id
        ).first()

        if content:
            content.paper_type = extraction.get("paper_type")
            content.topics = extraction.get("topics", [])
            content.one_sentence_summary = extraction.get("one_sentence_summary")
            content.key_findings = extraction.get("key_findings", [])
            content.methodology_summary = extraction.get("methodology_summary")
            content.extractor_model = model_name
            content.extraction_depth = depth
            content.extraction_date = datetime.utcnow()
            content.structured_data = structured_data
        else:
            content = PaperContent(
                paper_id=paper_id,
                paper_type=extraction.get("paper_type"),
                topics=extraction.get("topics", []),
                one_sentence_summary=extraction.get("one_sentence_summary"),
                key_findings=extraction.get("key_findings", []),
                methodology_summary=extraction.get("methodology_summary"),
                extractor_model=model_name,
                extraction_depth=depth,
                structured_data=structured_data,
            )
            session.add(content)

        session.commit()
        return True


async def extract_paper_multipass(paper_id: int, extractor: MultiPassExtractor,
                                   dry_run: bool = False, continue_from_notes: bool = False,
                                   apply_filter: bool = True) -> dict:
    """Run extraction on a paper (full multi-pass or quick abstract-only).

    Args:
        paper_id: Paper to extract
        extractor: MultiPassExtractor instance
        dry_run: If True, don't save anything
        continue_from_notes: If True, resume from saved chunk notes
        apply_filter: If True, skip full extraction for long irrelevant papers

    Returns:
        Dict with extraction result or error
    """
    print(f"\n{'='*60}")
    print(f"Extracting Paper {paper_id}")
    print(f"{'='*60}")

    # Get paper content
    try:
        title, abstract, chunks = get_paper_chunks(paper_id)
    except ValueError as e:
        return {"error": str(e)}

    # Check relevance
    relevance, matched_topics = score_relevance(title, abstract)
    chunk_count = len(chunks)
    do_full_extract = should_full_extract(relevance, chunk_count) if apply_filter else True

    print(f"  Title: {title[:60]}...")
    print(f"  Chunks: {chunk_count}")
    print(f"  Relevance: {relevance.upper()} ({len(matched_topics)} matches)")

    if not chunks:
        print(f"  No full text - abstract-only extraction")
        if dry_run:
            return {"status": "would_extract_abstract_only", "relevance": relevance}
        # Do quick abstract extraction
        result = await extractor.quick_extract_abstract(paper_id, title, abstract)
        if result.get("error"):
            return {"error": result["error"], "relevance": relevance}
        store_extraction(paper_id, result, is_quick=True)
        print(f"  DONE (quick): {result.get('paper_type')}")
        return {"status": "success_quick", "relevance": relevance, "paper_type": result.get("paper_type")}

    # Check if should skip full extraction
    if not do_full_extract:
        print(f"  SKIPPING full extraction (low relevance + {chunk_count} chunks)")
        print(f"  Doing quick abstract-only instead...")
        if dry_run:
            return {"status": "would_skip_full", "relevance": relevance, "chunks": chunk_count}
        result = await extractor.quick_extract_abstract(paper_id, title, abstract)
        if result.get("error"):
            return {"error": result["error"], "relevance": relevance}
        store_extraction(paper_id, result, is_quick=True)
        print(f"  DONE (quick): {result.get('paper_type')}")
        return {"status": "success_quick_skipped_full", "relevance": relevance, "chunks": chunk_count}

    # Check for existing notes if continuing
    chunk_notes = []
    start_chunk = 0

    if continue_from_notes:
        chunk_notes = get_saved_chunk_notes(paper_id)
        if chunk_notes:
            start_chunk = len(chunk_notes)
            print(f"  Resuming from chunk {start_chunk + 1} ({len(chunk_notes)} notes found)")

    # Process each chunk
    for i, chunk in enumerate(chunks[start_chunk:], start=start_chunk):
        chunk_num = i + 1
        print(f"  Processing chunk {chunk_num}/{len(chunks)}...", end=" ", flush=True)

        if dry_run:
            print("(dry run)")
            chunk_notes.append({"chunk_number": chunk_num, "dry_run": True})
            continue

        # Extract from chunk
        result = await extractor.extract_chunk(paper_id, chunk_num, chunk, title, abstract)

        if result.get("error"):
            print(f"ERROR: {result['error']}")
        else:
            print(f"OK ({result.get('section_type', 'unknown')})")
            # Save note immediately
            save_chunk_note(paper_id, chunk_num, result)
            chunk_notes.append(result)

    if dry_run:
        return {"status": "dry_run", "chunks": len(chunks)}

    # Consolidate all chunks
    print(f"\n  Consolidating {len(chunk_notes)} chunks...")
    final = await extractor.consolidate_chunks(paper_id, title, abstract, chunk_notes)

    if final.get("error"):
        print(f"  Consolidation ERROR: {final['error']}")
        return {"error": final["error"], "chunks_processed": len(chunk_notes)}

    # Store extraction
    print(f"  Storing extraction...")
    store_extraction(paper_id, final)

    # Clean up temp notes
    deleted = delete_chunk_notes(paper_id)
    print(f"  Cleaned up {deleted} temp notes")

    print(f"  DONE: {final.get('paper_type')} with {len(final.get('key_findings', []))} findings")

    return {
        "status": "success",
        "paper_type": final.get("paper_type"),
        "topics": final.get("topics", []),
        "chunks_processed": len(chunk_notes)
    }


def get_shallow_extractions(limit: int = 100) -> list[dict]:
    """Find papers that have extraction but it's likely shallow (abstract-only).

    Detects:
    - Papers with chunks but extraction has few key_findings
    - Papers where extractor_model doesn't include 'multipass'
    - Papers with short methodology_summary despite having full text

    Returns list of paper dicts needing re-extraction.
    """
    with get_session() as session:
        # Get papers with both chunks AND extraction
        results = session.execute(text("""
            SELECT
                p.id,
                p.title,
                COUNT(DISTINCT pch.id) as chunk_count,
                pc.extractor_model,
                pc.key_findings,
                pc.methodology_summary,
                pc.one_sentence_summary
            FROM papers p
            JOIN paper_chunks pch ON p.id = pch.paper_id
            JOIN paper_contents pc ON p.id = pc.paper_id
            GROUP BY p.id
            HAVING chunk_count > 2
            ORDER BY chunk_count DESC
            LIMIT :limit
        """), {"limit": limit * 3}).fetchall()  # Get more to filter

        shallow = []
        for row in results:
            paper_id, title, chunk_count, model, key_findings, methodology, summary = row

            # Parse key_findings if it's JSON string
            if isinstance(key_findings, str):
                try:
                    key_findings = json.loads(key_findings)
                except:
                    key_findings = []

            findings_count = len(key_findings) if key_findings else 0
            methodology_len = len(methodology) if methodology else 0

            # Heuristics for shallow extraction:
            # - Many chunks but few findings suggests didn't read full text
            # - Short methodology for multi-chunk paper
            is_shallow = False
            reason = []

            if chunk_count >= 5 and findings_count <= 3:
                is_shallow = True
                reason.append(f"{chunk_count} chunks but only {findings_count} findings")

            if chunk_count >= 3 and methodology_len < 200:
                is_shallow = True
                reason.append(f"short methodology ({methodology_len} chars) for {chunk_count} chunks")

            # Check if it was extracted with multipass
            if model and 'multipass' not in model.lower():
                if chunk_count >= 5:
                    is_shallow = True
                    reason.append(f"not multipass extracted ({model})")

            if is_shallow:
                shallow.append({
                    "id": paper_id,
                    "title": title[:60] + "..." if len(title) > 60 else title,
                    "chunk_count": chunk_count,
                    "findings_count": findings_count,
                    "methodology_len": methodology_len,
                    "model": model,
                    "reasons": reason
                })

            if len(shallow) >= limit:
                break

        return shallow


def get_papers_needing_work(limit: int = 50) -> tuple[list[dict], list[dict]]:
    """Get papers needing extraction work.

    Returns:
        (unextracted_papers, shallow_extractions)
    """
    from services.extraction_service import ExtractionService

    # Papers with no extraction at all
    unextracted = ExtractionService.get_papers_needing_extraction(limit=limit)

    # Papers with shallow extraction
    shallow = get_shallow_extractions(limit=limit)

    return unextracted, shallow


async def main():
    parser = argparse.ArgumentParser(description="Multi-pass extraction using Ollama")
    parser.add_argument("--paper-id", type=int, help="Extract specific paper")
    parser.add_argument("--batch", type=int, default=0, help="Extract N papers from queue")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--continue", dest="continue_run", action="store_true",
                       help="Resume from saved notes")
    parser.add_argument("--audit", action="store_true", help="Show papers needing work")
    parser.add_argument("--reextract-shallow", action="store_true",
                       help="Re-extract papers with shallow extractions")
    parser.add_argument("--no-filter", action="store_true",
                       help="Ignore relevance filter, extract all papers fully")
    args = parser.parse_args()

    extractor = MultiPassExtractor()

    # Check Ollama is available
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{extractor.host}/api/tags")
            if resp.status_code != 200:
                print("ERROR: Ollama not available")
                return
    except Exception as e:
        print(f"ERROR: Cannot connect to Ollama: {e}")
        return

    print(f"Using Ollama model: {extractor.model}")

    if args.audit:
        # Show papers needing work with relevance scoring
        unextracted, shallow = get_papers_needing_work(limit=100)

        print(f"\n{'='*70}")
        print("EXTRACTION AUDIT (with relevance filtering)")
        print(f"{'='*70}")

        # Score and categorize unextracted papers
        full_extract_needed = []
        quick_extract_only = []

        for p in unextracted:
            # Get paper details for relevance scoring
            with get_session() as session:
                paper = session.query(Paper).filter(Paper.id == p['id']).first()
                if paper:
                    relevance, topics = score_relevance(paper.title or "", paper.abstract or "")
                    chunk_count = session.query(PaperChunk).filter(
                        PaperChunk.paper_id == p['id']).count()
                    p['relevance'] = relevance
                    p['chunk_count'] = chunk_count
                    p['matched_topics'] = len(topics)

                    if should_full_extract(relevance, chunk_count):
                        full_extract_needed.append(p)
                    else:
                        quick_extract_only.append(p)

        print(f"\n## Need FULL Multi-Pass Extraction: {len(full_extract_needed)}")
        print("   (High/Medium relevance OR short papers)")
        for p in full_extract_needed[:15]:
            rel = p.get('relevance', '?').upper()
            chunks = p.get('chunk_count', '?')
            print(f"  [{p['id']}] [{rel}] {chunks} chunks: {p['title'][:45]}...")

        print(f"\n## Quick Abstract-Only (long, low relevance): {len(quick_extract_only)}")
        for p in quick_extract_only[:15]:
            rel = p.get('relevance', '?').upper()
            chunks = p.get('chunk_count', '?')
            print(f"  [{p['id']}] [{rel}] {chunks} chunks: {p['title'][:45]}...")

        # Score shallow extractions too
        shallow_relevant = []
        shallow_skip = []
        for p in shallow:
            with get_session() as session:
                paper = session.query(Paper).filter(Paper.id == p['id']).first()
                if paper:
                    relevance, _ = score_relevance(paper.title or "", paper.abstract or "")
                    p['relevance'] = relevance
                    if should_full_extract(relevance, p['chunk_count']):
                        shallow_relevant.append(p)
                    else:
                        shallow_skip.append(p)

        print(f"\n## Shallow Extractions - Need Re-extraction: {len(shallow_relevant)}")
        for p in shallow_relevant[:10]:
            rel = p.get('relevance', '?').upper()
            print(f"  [{p['id']}] [{rel}] {p['chunk_count']} chunks: {p['title'][:40]}...")
            print(f"       Reasons: {', '.join(p['reasons'][:2])}")

        print(f"\n## Shallow Extractions - Can Skip (low relevance): {len(shallow_skip)}")
        for p in shallow_skip[:10]:
            rel = p.get('relevance', '?').upper()
            print(f"  [{p['id']}] [{rel}] {p['chunk_count']} chunks: {p['title'][:40]}...")

        print(f"\n{'='*70}")
        print("SUMMARY:")
        print(f"  Full extraction needed: {len(full_extract_needed)} papers")
        print(f"  Quick abstract-only:    {len(quick_extract_only)} papers")
        print(f"  Re-extract shallow:     {len(shallow_relevant)} papers")
        print(f"  Skip (irrelevant):      {len(shallow_skip)} papers")
        print(f"{'='*70}")

    elif args.reextract_shallow:
        # Re-extract papers with shallow extractions (filtered by relevance)
        from services.extraction_service import ExtractionService

        shallow = get_shallow_extractions(limit=args.batch or 20)

        # Filter by relevance unless --no-filter
        apply_filter = not args.no_filter
        if apply_filter:
            relevant_shallow = []
            for p in shallow:
                with get_session() as session:
                    paper = session.query(Paper).filter(Paper.id == p['id']).first()
                    if paper:
                        relevance, _ = score_relevance(paper.title or "", paper.abstract or "")
                        if should_full_extract(relevance, p['chunk_count']):
                            relevant_shallow.append(p)
            shallow = relevant_shallow
            print(f"\nRe-extracting {len(shallow)} relevant shallow papers (filtered)...")
        else:
            print(f"\nRe-extracting {len(shallow)} shallow papers (no filter)...")

        for p in shallow:
            paper_id = p["id"]
            print(f"\n  Deleting old extraction for paper {paper_id}...")
            ExtractionService.delete_extraction(paper_id)

            result = await extract_paper_multipass(
                paper_id, extractor,
                dry_run=args.dry_run,
                continue_from_notes=args.continue_run,
                apply_filter=apply_filter
            )

            if result.get("error"):
                print(f"  Paper {paper_id}: FAILED - {result['error']}")
            else:
                print(f"  Paper {paper_id}: {result.get('status')}")

    elif args.paper_id:
        # Single paper
        apply_filter = not args.no_filter
        result = await extract_paper_multipass(
            args.paper_id, extractor,
            dry_run=args.dry_run,
            continue_from_notes=args.continue_run,
            apply_filter=apply_filter
        )
        print(f"\nResult: {json.dumps(result, indent=2)}")

    elif args.batch > 0:
        # Batch from queue
        from services.extraction_service import ExtractionService
        papers = ExtractionService.get_papers_needing_extraction(limit=args.batch)

        apply_filter = not args.no_filter
        print(f"\nProcessing {len(papers)} papers (filter={'OFF' if args.no_filter else 'ON'})...")

        stats = {"full": 0, "quick": 0, "failed": 0}
        for paper_info in papers:
            result = await extract_paper_multipass(
                paper_info["id"], extractor,
                dry_run=args.dry_run,
                continue_from_notes=args.continue_run,
                apply_filter=apply_filter
            )

            if result.get("error"):
                print(f"  Paper {paper_info['id']}: FAILED - {result['error']}")
                stats["failed"] += 1
            else:
                status = result.get('status', '')
                if 'quick' in status:
                    stats["quick"] += 1
                else:
                    stats["full"] += 1
                print(f"  Paper {paper_info['id']}: {status}")

        print(f"\nBatch complete: {stats['full']} full, {stats['quick']} quick, {stats['failed']} failed")
    else:
        print("Usage:")
        print("  --audit                   Show papers needing work (with relevance)")
        print("  --paper-id 123            Extract specific paper")
        print("  --batch 10                Extract 10 papers from queue")
        print("  --reextract-shallow       Re-extract shallow extractions")
        print("  --dry-run                 Show what would be done")
        print("  --continue                Resume from saved notes")
        print("  --no-filter               Ignore relevance, extract ALL papers fully")
        print("")
        print("Relevance filtering (default ON):")
        print("  - High/Medium relevance → Full multi-pass extraction")
        print("  - Low/None + ≤10 chunks → Full extraction (short anyway)")
        print("  - Low/None + >10 chunks → Quick abstract-only")
        print("")
        print("Examples:")
        print("  python -m scripts.multipass_extraction --audit")
        print("  python -m scripts.multipass_extraction --batch 50")
        print("  python -m scripts.multipass_extraction --batch 50 --no-filter  # Extract all fully")
        print("  python -m scripts.multipass_extraction --reextract-shallow --batch 20")


if __name__ == "__main__":
    asyncio.run(main())
