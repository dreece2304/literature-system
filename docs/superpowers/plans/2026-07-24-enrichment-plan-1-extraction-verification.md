# Enrichment Plan 1: Grounded Extraction + Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grounded deep extraction (quotes for every finding) with a tiered verification service that scores summaries 0–1, auto re-extracts borderline papers, persists scores, and exposes a review queue — plus the CLI batch runner.

**Architecture:** New stateless `VerificationService` (Tier 0 deterministic, Tier 1 MiniCheck NLI, Tier 2 cross-family judge) called after deep extraction; extraction prompts gain grounding-quote requirements; the dormant `ChunkProcessingState` gets wired into chunk prompts carrying facts only (sections + glossary); `src/scripts/enrich_pipeline.py` runs `backfill|extract|verify` stages overnight. Figures/tables and search integration are Plans 2 and 3.

**Tech Stack:** Python 3.11 (mamba env `litai`), SQLAlchemy + Alembic, Ollama HTTP API (httpx), pytest. Spec: `docs/superpowers/specs/2026-07-24-enrichment-pipeline-design.md`.

## Global Constraints

- Run all tests via: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest <path> -q`
- Line length 120; `from __future__ import annotations` in every new module; module docstrings with usage examples.
- Services are stateless class methods; MCP tools are thin wrappers; never query the DB directly from tools.
- Use `literature_core` helpers: `get_session`, `get_logger`, `success`/`error` response helpers, custom exceptions.
- Commit format: `<scope>: <type>: <description>` (e.g. `services: feat: Add VerificationService tier 0`).
- Models (already pulled locally): deep/reader `qwen3.5:9b`, quick `qwen3:4b-instruct-2507-q4_K_M`, verifier `bespoke-minicheck:7b`, judge `llama3.1:8b`.
- Verification thresholds: accept ≥ 0.85; re-extract once 0.60–0.85; below 0.60 after retry (or hard-gate fail) → review queue.
- Composite weights: 0.45 numeric fidelity, 0.35 claim support, 0.10 quote grounding, 0.10 judge pass.
- Deviation from spec (documented): unit handling is a co-occurrence window check, not `pint` conversion (YAGNI; spec updated to match).
- Alembic runs from `src/`: `cd src && /home/dreece23/miniforge3/bin/mamba run -n litai alembic upgrade head`.

---

### Task 1: Model config update

**Files:**
- Modify: `src/config/ai_settings.py:24-55` (OllamaSettings)
- Create: `tests/unit/config/__init__.py` (empty — the `tests/unit/config/` dir does not exist yet; every sibling test dir has one, so pytest needs it for collection)
- Test: `tests/unit/config/test_ai_settings.py` (new)

**Interfaces:**
- Produces: `settings.ollama.verifier_model: str`, `settings.ollama.judge_model: str`, `settings.ollama.vision_model: str`, `settings.ollama.chunk_num_ctx: int`, `settings.ollama.consolidation_num_ctx: int` — consumed by Tasks 6, 7, 10.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config/test_ai_settings.py
"""Tests for AI settings defaults (enrichment pipeline models)."""
from __future__ import annotations

from config.ai_settings import OllamaSettings


class TestOllamaModelDefaults:
    def test_extractor_models_updated(self):
        s = OllamaSettings()
        assert s.deep_extractor_model == "qwen3.5:9b"
        assert s.quick_extractor_model == "qwen3:4b-instruct-2507-q4_K_M"
        assert s.reader_model == "qwen3.5:9b"

    def test_new_pipeline_models(self):
        s = OllamaSettings()
        assert s.verifier_model == "bespoke-minicheck:7b"
        assert s.judge_model == "llama3.1:8b"
        assert s.vision_model == "qwen3.5:9b"

    def test_context_windows(self):
        s = OllamaSettings()
        assert s.chunk_num_ctx == 16384
        assert s.consolidation_num_ctx == 32768
```

- [ ] **Step 1b: Create the config test package init**

```bash
mkdir -p tests/unit/config && touch tests/unit/config/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/config/test_ai_settings.py -q`
Expected: FAIL (`verifier_model` attribute error / wrong defaults)

- [ ] **Step 3: Update OllamaSettings**

In `src/config/ai_settings.py`, change defaults and add fields inside `OllamaSettings`:

```python
    reader_model: str = Field(default="qwen3.5:9b", description="Model for Q&A and extraction")

    # Extraction-specific models (two-tier system)
    quick_extractor_model: str = Field(
        default="qwen3:4b-instruct-2507-q4_K_M",
        description="Fast model for quick extraction (abstract-only: type, topics, summary)"
    )
    deep_extractor_model: str = Field(
        default="qwen3.5:9b",
        description="Full model for deep extraction (PDF: findings, methodology, claims)"
    )

    # Enrichment pipeline models (spec 2026-07-24)
    verifier_model: str = Field(
        default="bespoke-minicheck:7b",
        description="NLI fact-checker for claim-vs-source verification (binary Yes/No)"
    )
    judge_model: str = Field(
        default="llama3.1:8b",
        description="Cross-family judge for borderline verification (binary questions only)"
    )
    vision_model: str = Field(
        default="qwen3.5:9b",
        description="Multimodal model for figure analysis (qwen3.5 accepts image input)"
    )

    # Context windows (Ollama silently truncates prompts beyond num_ctx)
    chunk_num_ctx: int = Field(default=16384, description="num_ctx for per-chunk extraction calls")
    consolidation_num_ctx: int = Field(default=32768, description="num_ctx for consolidation calls")
```

Leave `writer_model`/`triager_model` untouched (legacy, out of scope).

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/config/test_ai_settings.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/config/ai_settings.py tests/unit/config/test_ai_settings.py
git commit -m "config: feat: Update model defaults, add verifier/judge/vision models and num_ctx settings"
```

---

### Task 2: Migration — verification_score + extraction checkpoint

**Files:**
- Create: `src/alembic/versions/<autogen>_add_verification_score_and_checkpoint.py`
- Modify: `src/literature_core/models.py:275` (PaperContent), ExtractionMetadata model (same file, search `class ExtractionMetadata`)
- Test: `tests/unit/literature_core/test_verification_columns.py` (new)

**Interfaces:**
- Produces: `PaperContent.verification_score: float | None` (indexed), `ExtractionMetadata.extraction_checkpoint: dict | None` — consumed by Tasks 8, 10, 12, 13.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/literature_core/test_verification_columns.py
"""Tests for verification_score and extraction_checkpoint columns."""
from __future__ import annotations

from literature_core.models import ExtractionMetadata, PaperContent


class TestVerificationColumns:
    def test_paper_content_has_verification_score(self, db):
        content = PaperContent(paper_id=1, verification_score=0.87)
        assert content.verification_score == 0.87

    def test_extraction_metadata_has_checkpoint(self, db):
        meta = ExtractionMetadata(paper_id=1, extraction_checkpoint={"chunks_processed": 3})
        assert meta.extraction_checkpoint == {"chunks_processed": 3}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/literature_core/test_verification_columns.py -q`
Expected: FAIL (TypeError: invalid keyword argument)

- [ ] **Step 3: Add columns to models**

In `src/literature_core/models.py`, under the existing `verification = Column(JSON)` line in `PaperContent`:

```python
    verification_score = Column(Float, index=True)  # 0-1 composite; null = never verified
```

(ensure `Float` is in the existing `sqlalchemy` import list). In `ExtractionMetadata`, after `chunking_queued_at`:

```python
    extraction_checkpoint = Column(JSON)  # ChunkProcessingState snapshot for crash recovery
```

- [ ] **Step 4: Generate + apply migration**

```bash
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai alembic revision --autogenerate -m "add verification_score and extraction_checkpoint"
cd src && /home/dreece23/miniforge3/bin/mamba run -n litai alembic upgrade head
```

Inspect the generated file: it must contain exactly two `add_column` calls (+ index) — remove any unrelated autogen noise.

- [ ] **Step 5: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/literature_core/test_verification_columns.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/literature_core/models.py src/alembic/versions/
git commit -m "db: feat: Add verification_score and extraction_checkpoint columns"
```

---

### Task 3: VerificationService Tier 0 — quote matching

**Files:**
- Create: `src/services/verification_service.py`
- Test: `tests/unit/services/test_verification_quotes.py` (new)

**Interfaces:**
- Produces: `QuoteMatch` dataclass (`found: bool, method: str, score: float, excerpt: str`) and `VerificationService.match_quote(quote: str, source: str) -> QuoteMatch`. Methods: `"exact"`, `"numeric"`, `"fuzzy"`, `"none"`. Consumed by Tasks 4, 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_verification_quotes.py
"""Tests for Tier 0 quote matching (exact -> numeric -> fuzzy)."""
from __future__ import annotations

from services.verification_service import VerificationService

SOURCE = (
    "The membrane exhibited a water flux of 42.7 L/m2/h at 5 bar. "
    "Contact angle decreased from 78.3 degrees to 45.1 degrees after coating. "
    "XPS confirmed zinc incorporation of 12.4 at.% in the modified films."
)


class TestMatchQuote:
    def test_exact_match(self):
        m = VerificationService.match_quote("water flux of 42.7 L/m2/h at 5 bar", SOURCE)
        assert m.found and m.method == "exact" and m.score == 1.0

    def test_numeric_match_survives_paraphrase(self):
        # Quote paraphrased but numbers preserved
        m = VerificationService.match_quote("flux was 42.7 at a pressure of 5 bar", SOURCE)
        assert m.found and m.method in ("numeric", "fuzzy")

    def test_fuzzy_match_minor_ocr_noise(self):
        m = VerificationService.match_quote("Contact angle decreased frorn 78.3 degrees to 45.1 degrees", SOURCE)
        assert m.found and m.score >= 0.85

    def test_fabricated_quote_rejected(self):
        m = VerificationService.match_quote("thermal stability improved by 300 percent", SOURCE)
        assert not m.found and m.method == "none"

    def test_empty_quote_rejected(self):
        m = VerificationService.match_quote("", SOURCE)
        assert not m.found
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_quotes.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement quote matching**

```python
# src/services/verification_service.py
"""Verification Service - scores LLM extractions against source text.

Tiered design (spec 2026-07-24): Tier 0 deterministic (quotes, numbers),
Tier 1 NLI claim support (bespoke-minicheck), Tier 2 cross-family judge for
borderline papers. Composite 0-1 score persisted to PaperContent.

Usage:
    from services.verification_service import VerificationService

    m = VerificationService.match_quote(quote, source_text)
    result = VerificationService.verify_paper(paper_id)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from literature_core import get_logger

logger = get_logger(__name__)

FUZZY_THRESHOLD = 0.85


@dataclass
class QuoteMatch:
    """Result of matching a grounding quote against source text."""
    found: bool
    method: str          # "exact" | "numeric" | "fuzzy" | "none"
    score: float         # 0-1 match quality
    excerpt: str = ""    # matched source window (for evidence)


class VerificationService:
    """Stateless verification of extractions against source text."""

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.strip().lower())

    @staticmethod
    def _numbers_in(text: str) -> list[str]:
        return re.findall(r"\d+(?:[.,]\d+)?", text)

    @classmethod
    def match_quote(cls, quote: str, source: str) -> QuoteMatch:
        """Match a quote: exact substring -> all-numbers-present -> fuzzy window."""
        if not quote or not quote.strip():
            return QuoteMatch(found=False, method="none", score=0.0)
        q_norm, s_norm = cls._normalize(quote), cls._normalize(source)

        idx = s_norm.find(q_norm)
        if idx != -1:
            return QuoteMatch(found=True, method="exact", score=1.0,
                              excerpt=source[max(0, idx - 50):idx + len(quote) + 50])

        nums = cls._numbers_in(quote)
        if nums and all(n in s_norm for n in nums):
            first = s_norm.find(nums[0])
            return QuoteMatch(found=True, method="numeric", score=0.9,
                              excerpt=source[max(0, first - 100):first + 150])

        best, best_pos = 0.0, 0
        window = max(len(q_norm), 40)
        step = max(window // 4, 10)
        for pos in range(0, max(len(s_norm) - window // 2, 1), step):
            ratio = SequenceMatcher(None, q_norm, s_norm[pos:pos + window]).ratio()
            if ratio > best:
                best, best_pos = ratio, pos
        if best >= FUZZY_THRESHOLD:
            return QuoteMatch(found=True, method="fuzzy", score=round(best, 3),
                              excerpt=source[best_pos:best_pos + window])
        return QuoteMatch(found=False, method="none", score=round(best, 3))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_quotes.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/services/verification_service.py tests/unit/services/test_verification_quotes.py
git commit -m "services: feat: Add VerificationService Tier 0 quote matching"
```

---

### Task 4: Tier 0 — number extraction and alignment

**Files:**
- Modify: `src/services/verification_service.py`
- Test: `tests/unit/services/test_verification_numbers.py` (new)

**Interfaces:**
- Produces: `NumberCheck` dataclass (`value: str, matched: bool, context: str`) and `VerificationService.check_numbers(claim_text: str, source: str) -> list[NumberCheck]`; `VerificationService.numeric_fidelity(checks: list[NumberCheck]) -> float` (1.0 when no numbers). Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_verification_numbers.py
"""Tests for Tier 0 numeric fidelity (normalization + source alignment)."""
from __future__ import annotations

from services.verification_service import VerificationService

SOURCE = "Conversion reached 87.5% after 2h. The film thickness was 1,250 nm (1.25e3 nm nominal)."


class TestCheckNumbers:
    def test_plain_and_percent(self):
        checks = VerificationService.check_numbers("conversion of 87.5%", SOURCE)
        assert len(checks) == 1 and checks[0].matched

    def test_thousands_separator_normalized(self):
        checks = VerificationService.check_numbers("thickness of 1250 nm", SOURCE)
        assert checks[0].matched  # 1250 matches "1,250"

    def test_scientific_notation_normalized(self):
        checks = VerificationService.check_numbers("nominal 1.25e3 nm", SOURCE)
        assert checks[0].matched

    def test_hallucinated_number_flagged(self):
        checks = VerificationService.check_numbers("yield of 99.9%", SOURCE)
        assert not checks[0].matched

    def test_fidelity_score(self):
        checks = VerificationService.check_numbers("87.5% and 99.9%", SOURCE)
        assert VerificationService.numeric_fidelity(checks) == 0.5

    def test_fidelity_no_numbers_is_one(self):
        assert VerificationService.numeric_fidelity([]) == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_numbers.py -q`
Expected: FAIL (AttributeError: check_numbers)

- [ ] **Step 3: Implement number alignment**

Add to `src/services/verification_service.py`:

```python
@dataclass
class NumberCheck:
    """One extracted number checked against source."""
    value: str           # as written in the claim
    matched: bool
    context: str = ""    # source window around the match


NUM_RE = re.compile(r"\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?")


class VerificationService:  # (methods added to the existing class)

    @staticmethod
    def _canonical_number(token: str) -> float | None:
        try:
            return float(token.replace(",", ""))
        except ValueError:
            return None

    @classmethod
    def _source_number_set(cls, source: str) -> dict[float, str]:
        out: dict[float, str] = {}
        for m in NUM_RE.finditer(source):
            v = cls._canonical_number(m.group())
            if v is not None and v not in out:
                out[v] = source[max(0, m.start() - 60):m.end() + 60]
        return out

    @classmethod
    def check_numbers(cls, claim_text: str, source: str) -> list[NumberCheck]:
        """Every number in claim_text must exist in source (normalized compare)."""
        source_nums = cls._source_number_set(source)
        checks = []
        for m in NUM_RE.finditer(claim_text):
            v = cls._canonical_number(m.group())
            if v is None:
                continue
            ctx = source_nums.get(v, "")
            checks.append(NumberCheck(value=m.group(), matched=v in source_nums, context=ctx))
        return checks

    @staticmethod
    def numeric_fidelity(checks: list[NumberCheck]) -> float:
        if not checks:
            return 1.0
        return sum(1 for c in checks if c.matched) / len(checks)
```

Note: `1.25e3` and `1,250` both canonicalize to `1250.0`, so normalization is exact-value equality after parsing. Deduplicate nothing — every occurrence counts.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_numbers.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/services/verification_service.py tests/unit/services/test_verification_numbers.py
git commit -m "services: feat: Add Tier 0 numeric fidelity checks"
```

---

### Task 5: Composite scoring and routing

**Files:**
- Modify: `src/services/verification_service.py`
- Test: `tests/unit/services/test_verification_scoring.py` (new)

**Interfaces:**
- Produces: `VerificationService.composite_score(numeric: float, claim_support: float, quote_grounding: float, judge_pass: float, hard_gate_failed: bool) -> float` and `VerificationService.route(score: float, retried: bool) -> str` returning `"accept" | "reextract" | "review"`. Constants `ACCEPT_THRESHOLD = 0.85`, `RETRY_THRESHOLD = 0.60`. Consumed by Tasks 8, 11, 13.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_verification_scoring.py
"""Tests for composite verification score and routing policy."""
from __future__ import annotations

import pytest

from services.verification_service import VerificationService


class TestCompositeScore:
    def test_weights(self):
        s = VerificationService.composite_score(1.0, 1.0, 1.0, 1.0, hard_gate_failed=False)
        assert s == 1.0
        s = VerificationService.composite_score(1.0, 0.0, 0.0, 0.0, hard_gate_failed=False)
        assert s == pytest.approx(0.45)

    def test_hard_gate_zeroes(self):
        s = VerificationService.composite_score(1.0, 1.0, 1.0, 1.0, hard_gate_failed=True)
        assert s == 0.0


class TestRouting:
    def test_accept(self):
        assert VerificationService.route(0.9, retried=False) == "accept"

    def test_borderline_first_pass_reextracts(self):
        assert VerificationService.route(0.7, retried=False) == "reextract"

    def test_borderline_after_retry_reviews(self):
        assert VerificationService.route(0.7, retried=True) == "review"

    def test_low_always_reviews(self):
        assert VerificationService.route(0.3, retried=False) == "review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_scoring.py -q`
Expected: FAIL

- [ ] **Step 3: Implement scoring + routing**

Add to `VerificationService`:

```python
    ACCEPT_THRESHOLD = 0.85
    RETRY_THRESHOLD = 0.60

    W_NUMERIC, W_CLAIMS, W_QUOTES, W_JUDGE = 0.45, 0.35, 0.10, 0.10

    @classmethod
    def composite_score(cls, numeric: float, claim_support: float, quote_grounding: float,
                        judge_pass: float, hard_gate_failed: bool) -> float:
        if hard_gate_failed:
            return 0.0
        return round(cls.W_NUMERIC * numeric + cls.W_CLAIMS * claim_support
                     + cls.W_QUOTES * quote_grounding + cls.W_JUDGE * judge_pass, 3)

    @classmethod
    def route(cls, score: float, retried: bool) -> str:
        if score >= cls.ACCEPT_THRESHOLD:
            return "accept"
        if score >= cls.RETRY_THRESHOLD and not retried:
            return "reextract"
        return "review"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_scoring.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/services/verification_service.py tests/unit/services/test_verification_scoring.py
git commit -m "services: feat: Add composite verification scoring and routing policy"
```

---

### Task 6: Tier 1 — MiniCheck client

**Files:**
- Modify: `src/services/verification_service.py`
- Test: `tests/unit/services/test_verification_minicheck.py` (new)

**Interfaces:**
- Consumes: `settings.ollama.verifier_model`, `settings.ollama.host` (Task 1).
- Produces: `MiniCheckClient` with `is_available() -> bool` and `check_claim(claim: str, document: str) -> bool | None` (None = call failed); `VerificationService.claim_support(claims: list[str], chunks: list[str], client: MiniCheckClient) -> tuple[float, list[dict]]` returning (fraction supported, per-claim evidence). Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_verification_minicheck.py
"""Tests for Tier 1 claim support via MiniCheck (mocked HTTP)."""
from __future__ import annotations

from unittest.mock import patch

from services.verification_service import MiniCheckClient, VerificationService


class FakeMiniCheck(MiniCheckClient):
    """Answers Yes iff the claim's first 5 words appear in the document."""
    def __init__(self, answers: dict[str, bool]):
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def check_claim(self, claim: str, document: str) -> bool | None:
        self.calls.append((claim, document))
        return self.answers.get(claim)


class TestClaimSupport:
    def test_supported_fraction(self):
        client = FakeMiniCheck({"claim A": True, "claim B": False})
        frac, evidence = VerificationService.claim_support(
            ["claim A", "claim B"], ["chunk one text", "chunk two text"], client)
        assert frac == 0.5
        assert evidence[0]["supported"] is True and evidence[1]["supported"] is False

    def test_claim_checked_against_best_chunks_first(self):
        client = FakeMiniCheck({"the zinc film grew fast": True})
        frac, _ = VerificationService.claim_support(
            ["the zinc film grew fast"],
            ["unrelated text about solvents", "zinc film growth was rapid"], client)
        assert frac == 1.0
        # First document tried should be the token-overlap-ranked best chunk
        assert "zinc" in client.calls[0][1]

    def test_failed_calls_dont_count_as_supported(self):
        client = FakeMiniCheck({})  # returns None for everything
        frac, evidence = VerificationService.claim_support(["c1"], ["chunk"], client)
        assert frac == 0.0 and evidence[0]["supported"] is None

    def test_no_claims_is_full_support(self):
        client = FakeMiniCheck({})
        frac, evidence = VerificationService.claim_support([], ["chunk"], client)
        assert frac == 1.0 and evidence == []


class TestMiniCheckClientParse:
    @patch("services.verification_service.MiniCheckClient._generate")
    def test_yes_parsed(self, mock_gen):
        mock_gen.return_value = "Yes"
        assert MiniCheckClient().check_claim("c", "d") is True

    @patch("services.verification_service.MiniCheckClient._generate")
    def test_no_parsed(self, mock_gen):
        mock_gen.return_value = "No, the document does not support this."
        assert MiniCheckClient().check_claim("c", "d") is False

    @patch("services.verification_service.MiniCheckClient._generate")
    def test_error_returns_none(self, mock_gen):
        mock_gen.return_value = None
        assert MiniCheckClient().check_claim("c", "d") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_minicheck.py -q`
Expected: FAIL (ImportError: MiniCheckClient)

- [ ] **Step 3: Implement MiniCheck client + claim_support**

Add to `src/services/verification_service.py` (imports: `import httpx`, `from config.ai_settings import settings`):

```python
class MiniCheckClient:
    """Ollama client for bespoke-minicheck fact checking.

    bespoke-minicheck expects: "Document: {doc}\nClaim: {claim}" and answers Yes/No.
    """

    def __init__(self):
        self.host = settings.ollama.host
        self.model = settings.ollama.verifier_model
        self.timeout = settings.ollama.timeout

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=5) as client:
                r = client.get(f"{self.host}/api/tags")
                return r.status_code == 200 and self.model.split(":")[0] in r.text
        except Exception:
            return False

    def _generate(self, prompt: str) -> str | None:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(f"{self.host}/api/generate", json={
                    "model": self.model, "prompt": prompt, "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 4},
                })
                if r.status_code != 200:
                    return None
                return r.json().get("response", "")
        except Exception as e:
            logger.warning("MiniCheck call failed", extra={"error": str(e)})
            return None

    def check_claim(self, claim: str, document: str) -> bool | None:
        resp = self._generate(f"Document: {document}\nClaim: {claim}")
        if resp is None:
            return None
        return resp.strip().lower().startswith("yes")
```

And on `VerificationService`:

```python
    TOP_CHUNKS_PER_CLAIM = 3

    @staticmethod
    def _rank_chunks(claim: str, chunks: list[str]) -> list[str]:
        claim_tokens = set(re.findall(r"[a-z0-9]+", claim.lower()))
        scored = [(len(claim_tokens & set(re.findall(r"[a-z0-9]+", c.lower()))), c) for c in chunks]
        scored.sort(key=lambda t: -t[0])
        return [c for _, c in scored]

    @classmethod
    def claim_support(cls, claims: list[str], chunks: list[str],
                      client: MiniCheckClient) -> tuple[float, list[dict]]:
        """Fraction of claims supported by their best-matching chunks."""
        if not claims:
            return 1.0, []
        evidence = []
        supported = 0
        for claim in claims:
            verdict: bool | None = None
            for chunk in cls._rank_chunks(claim, chunks)[:cls.TOP_CHUNKS_PER_CLAIM]:
                verdict = client.check_claim(claim, chunk)
                if verdict:
                    break
            if verdict:
                supported += 1
            evidence.append({"claim": claim, "supported": verdict})
        return supported / len(claims), evidence
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_minicheck.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/services/verification_service.py tests/unit/services/test_verification_minicheck.py
git commit -m "services: feat: Add Tier 1 MiniCheck claim-support client"
```

---

### Task 7: Tier 2 — cross-family judge (binary questions)

**Files:**
- Modify: `src/services/verification_service.py`
- Test: `tests/unit/services/test_verification_judge.py` (new)

**Interfaces:**
- Consumes: `settings.ollama.judge_model` (Task 1).
- Produces: `JudgeClient` with `ask_binary(question: str, summary: str, abstract: str) -> bool | None`; `VerificationService.judge_pass(summary: str, key_findings: list[str], abstract: str, client: JudgeClient) -> tuple[float, list[dict]]`. Judge is only invoked by Task 8 for borderline papers; `judge_pass` returns fraction of questions answered acceptably (unanswerable calls count as pass — fail-open, judge is a 0.10-weight signal). Consumed by Task 8.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_verification_judge.py
"""Tests for Tier 2 cross-family binary judge."""
from __future__ import annotations

from services.verification_service import JudgeClient, VerificationService


class FakeJudge(JudgeClient):
    def __init__(self, verdicts: list[bool | None]):
        self.verdicts = list(verdicts)
        self.questions: list[str] = []

    def ask_binary(self, question: str, summary: str, abstract: str) -> bool | None:
        self.questions.append(question)
        return self.verdicts.pop(0)


class TestJudgePass:
    def test_all_pass(self):
        client = FakeJudge([True, True, True])
        score, answers = VerificationService.judge_pass("sum", ["f1"], "abs", client)
        assert score == 1.0 and len(answers) == 3

    def test_invented_conclusion_fails(self):
        # Q2 asks "does the summary contain conclusions absent from the source?"
        # judge answering True there = invented conclusion = fail for that question
        client = FakeJudge([True, True, False])
        score, _ = VerificationService.judge_pass("sum", ["f1"], "abs", client)
        assert score < 1.0

    def test_none_counts_as_pass_fail_open(self):
        client = FakeJudge([None, None, None])
        score, answers = VerificationService.judge_pass("sum", ["f1"], "abs", client)
        assert score == 1.0
        assert all(a["verdict"] is None for a in answers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_judge.py -q`
Expected: FAIL (ImportError: JudgeClient)

- [ ] **Step 3: Implement judge**

Add to `src/services/verification_service.py`:

```python
class JudgeClient:
    """Cross-family binary judge (llama3.1). Binary questions only - never rubric scores."""

    def __init__(self):
        self.host = settings.ollama.host
        self.model = settings.ollama.judge_model
        self.timeout = settings.ollama.timeout

    def ask_binary(self, question: str, summary: str, abstract: str) -> bool | None:
        prompt = (
            "You are checking a machine-generated summary of a scientific paper.\n"
            f"Paper abstract:\n{abstract}\n\nGenerated summary and findings:\n{summary}\n\n"
            f"Question: {question}\nAnswer with exactly one word: Yes or No."
        )
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(f"{self.host}/api/generate", json={
                    "model": self.model, "prompt": prompt, "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 4},
                })
                if r.status_code != 200:
                    return None
                return r.json().get("response", "").strip().lower().startswith("yes")
        except Exception as e:
            logger.warning("Judge call failed", extra={"error": str(e)})
            return None
```

And on `VerificationService` — questions paired with the verdict that counts as PASS:

```python
    # (question, verdict_that_means_pass)
    JUDGE_QUESTIONS = [
        ("Does the summary state the paper's main finding?", True),
        ("Is the summary consistent with the abstract?", True),
        ("Does the summary contain any conclusion that is absent from the abstract and findings?", False),
    ]

    @classmethod
    def judge_pass(cls, summary: str, key_findings: list[str], abstract: str,
                   client: JudgeClient) -> tuple[float, list[dict]]:
        text = summary + "\nFindings:\n" + "\n".join(f"- {f}" for f in key_findings)
        answers = []
        passed = 0
        for question, pass_verdict in cls.JUDGE_QUESTIONS:
            verdict = client.ask_binary(question, text, abstract)
            ok = verdict is None or verdict == pass_verdict  # fail-open on call failure
            passed += ok
            answers.append({"question": question, "verdict": verdict, "pass": ok})
        return passed / len(cls.JUDGE_QUESTIONS), answers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_judge.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/services/verification_service.py tests/unit/services/test_verification_judge.py
git commit -m "services: feat: Add Tier 2 cross-family binary judge"
```

---

### Task 8: verify_paper orchestration + persistence

**Files:**
- Modify: `src/services/verification_service.py`
- Test: `tests/unit/services/test_verification_verify_paper.py` (new)

**Interfaces:**
- Consumes: everything from Tasks 3–7; `PaperContent.verification_score` (Task 2); `ExtractionService.get_all_chunks(paper_id) -> list[dict]` (existing, keys include `content`).
- Produces: `VerificationService.verify_paper(paper_id: int, minicheck: MiniCheckClient | None = None, judge: JudgeClient | None = None, retried: bool = False) -> dict` with keys `paper_id, score, routing, numeric_fidelity, claim_support, quote_grounding, judge_pass, hard_gate_failed, failures (list[str]), evidence (dict)`. Persists `verification` JSON + `verification_score` on PaperContent. Raises `PaperNotFoundError` for missing paper. Consumed by Tasks 11, 12, 13.

Verification inputs read from PaperContent: summary = `deep_one_sentence_summary or one_sentence_summary`; claims = `key_findings` list; numbers checked per finding; quotes = each finding dict's `quote` key when findings are dicts (grounded schema from Task 9), else quote_grounding = 1.0 for legacy string findings (no quotes to check ≠ hard fail; legacy papers score on the other components).

Hard gates: no chunks AND no abstract (nothing to verify against) → error dict, not exception; findings are grounded dicts and >50% of quotes unmatched; any number in a finding unmatched AND `retried=True`.

Tier 2 runs only when the Tier 0+1 provisional score (with judge_pass=1.0) lands in [0.60, 0.85).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_verification_verify_paper.py
"""Integration-style tests for verify_paper (DB + fake clients)."""
from __future__ import annotations

import pytest

from literature_core import PaperNotFoundError, get_session
from literature_core.models import Paper, PaperChunk, PaperContent
from services.verification_service import VerificationService

from .test_verification_minicheck import FakeMiniCheck
from .test_verification_judge import FakeJudge

SOURCE = "Water flux reached 42.7 L/m2/h. Contact angle fell to 45.1 degrees."


@pytest.fixture
def grounded_paper(db):
    with get_session() as s:
        p = Paper(title="Test membrane paper", abstract="Flux and wetting study.")
        s.add(p)
        s.flush()
        s.add(PaperChunk(paper_id=p.id, chunk_order=1, content=SOURCE,
                         word_count=11, char_count=len(SOURCE)))
        s.add(PaperContent(
            paper_id=p.id,
            deep_one_sentence_summary="Membrane flux hit 42.7 L/m2/h with contact angle 45.1.",
            key_findings=[
                {"finding": "Flux reached 42.7 L/m2/h",
                 "quote": "Water flux reached 42.7 L/m2/h"},
                {"finding": "Contact angle fell to 45.1 degrees",
                 "quote": "Contact angle fell to 45.1 degrees"},
            ],
        ))
        s.commit()
        return p.id


class TestVerifyPaper:
    def test_clean_paper_accepts_and_persists(self, grounded_paper):
        mc = FakeMiniCheck({"Flux reached 42.7 L/m2/h": True,
                            "Contact angle fell to 45.1 degrees": True})
        result = VerificationService.verify_paper(grounded_paper, minicheck=mc)
        assert result["score"] >= 0.85 and result["routing"] == "accept"
        with get_session() as s:
            content = s.query(PaperContent).filter_by(paper_id=grounded_paper).first()
            assert content.verification_score == result["score"]
            assert content.verification["routing"] == "accept"

    def test_hallucinated_number_lowers_score(self, grounded_paper):
        with get_session() as s:
            c = s.query(PaperContent).filter_by(paper_id=grounded_paper).first()
            c.key_findings = [{"finding": "Flux reached 99.9 L/m2/h",
                               "quote": "Water flux reached 99.9 L/m2/h"}]
            s.commit()
        mc = FakeMiniCheck({"Flux reached 99.9 L/m2/h": False})
        result = VerificationService.verify_paper(grounded_paper, minicheck=mc)
        assert result["numeric_fidelity"] < 1.0
        assert result["routing"] in ("reextract", "review")

    def test_borderline_invokes_judge(self, grounded_paper):
        mc = FakeMiniCheck({"Flux reached 42.7 L/m2/h": True,
                            "Contact angle fell to 45.1 degrees": False})
        judge = FakeJudge([True, True, True])
        VerificationService.verify_paper(grounded_paper, minicheck=mc, judge=judge)
        assert len(judge.questions) == 3  # borderline -> judge consulted

    def test_missing_paper_raises(self, db):
        with pytest.raises(PaperNotFoundError):
            VerificationService.verify_paper(999999)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_verify_paper.py -q`
Expected: FAIL (AttributeError: verify_paper)

- [ ] **Step 3: Implement verify_paper**

Add to `VerificationService` (imports: `from datetime import datetime, timezone`; `from literature_core import PaperNotFoundError, get_session`; `from literature_core.models import Paper, PaperContent`):

```python
    @classmethod
    def verify_paper(cls, paper_id: int, minicheck: MiniCheckClient | None = None,
                     judge: JudgeClient | None = None, retried: bool = False) -> dict:
        """Run tiered verification for one paper's extraction; persist score + evidence."""
        from services.extraction_service import ExtractionService

        with get_session() as session:
            paper = session.query(Paper).get(paper_id)
            if not paper:
                raise PaperNotFoundError(paper_id)
            content = session.query(PaperContent).filter_by(paper_id=paper_id).first()
            if not content:
                return {"paper_id": paper_id, "error": "No extraction to verify"}
            abstract = paper.abstract or ""
            summary = content.deep_one_sentence_summary or content.one_sentence_summary or ""
            findings = content.key_findings or []

        chunks = [c["content"] for c in ExtractionService.get_all_chunks(paper_id)]
        source = " ".join(chunks) or abstract
        if not source:
            return {"paper_id": paper_id, "error": "No source text (chunks or abstract)"}

        failures: list[str] = []

        # --- Tier 0 ---
        grounded = [f for f in findings if isinstance(f, dict)]
        legacy = [f for f in findings if isinstance(f, str)]
        quote_results = [cls.match_quote(f.get("quote", ""), source) for f in grounded]
        quote_grounding = (
            sum(1 for q in quote_results if q.found) / len(quote_results)
            if quote_results else 1.0
        )
        for f, q in zip(grounded, quote_results):
            if not q.found:
                failures.append(f"quote unmatched: {f.get('quote', '')[:80]}")

        claim_texts = [f.get("finding", "") for f in grounded] + legacy
        number_checks = [c for t in claim_texts for c in cls.check_numbers(t, source)]
        numeric = cls.numeric_fidelity(number_checks)
        failures += [f"number unmatched: {c.value}" for c in number_checks if not c.matched]

        hard_gate = (
            (quote_results and quote_grounding < 0.5)
            or (retried and any(not c.matched for c in number_checks))
        )

        # --- Tier 1 ---
        minicheck = minicheck or MiniCheckClient()
        claim_frac, claim_evidence = cls.claim_support(
            [t for t in claim_texts if t] + ([summary] if summary else []),
            chunks or [source], minicheck)
        failures += [f"claim unsupported: {e['claim'][:80]}"
                     for e in claim_evidence if e["supported"] is False]

        # --- Tier 2 (borderline only) ---
        provisional = cls.composite_score(numeric, claim_frac, quote_grounding, 1.0, hard_gate)
        judge_frac, judge_answers = 1.0, []
        if cls.RETRY_THRESHOLD <= provisional < cls.ACCEPT_THRESHOLD:
            judge_frac, judge_answers = cls.judge_pass(
                summary, claim_texts, abstract, judge or JudgeClient())

        score = cls.composite_score(numeric, claim_frac, quote_grounding, judge_frac, hard_gate)
        routing = cls.route(score, retried)

        result = {
            "paper_id": paper_id, "score": score, "routing": routing,
            "numeric_fidelity": round(numeric, 3), "claim_support": round(claim_frac, 3),
            "quote_grounding": round(quote_grounding, 3), "judge_pass": round(judge_frac, 3),
            "hard_gate_failed": hard_gate, "failures": failures,
            "evidence": {"claims": claim_evidence, "judge": judge_answers},
        }

        with get_session() as session:
            content = session.query(PaperContent).filter_by(paper_id=paper_id).first()
            content.verification_score = score
            content.verification = {**result, "verified_at": datetime.now(timezone.utc).isoformat(),
                                    "retried": retried}
            session.commit()

        logger.info("Verified paper", extra={"paper_id": paper_id, "score": score,
                                             "routing": routing})
        return result
```

Note: `PaperChunk` model name — confirm in `src/literature_core/models.py` (table `paper_chunks`); adjust the test import if the class is named differently.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_verification_verify_paper.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Run full verification test file set**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/ -q -k verification`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/services/verification_service.py tests/unit/services/test_verification_verify_paper.py
git commit -m "services: feat: Add verify_paper orchestration with persistence and routing"
```

---

### Task 9: Grounded extraction prompts

**Files:**
- Modify: `src/services/extraction_prompts.py:251` (CHUNK_EXTRACTION_PROMPT), `:342` (CONSOLIDATION_PROMPT), `get_consolidation_prompt` (~line 860)
- Test: `tests/unit/services/test_extraction_prompts_grounding.py` (new)

**Interfaces:**
- Produces: chunk prompt instructs `key_findings` as objects `{"finding": str, "quote": str}` and a `defined_terms` object (abbreviation → expansion); consolidation prompt preserves quotes and accepts optional `corrections: str | None` parameter appended as a CORRECTIONS section. Consumed by Tasks 10, 11.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_extraction_prompts_grounding.py
"""Tests for grounding-quote requirements in extraction prompts."""
from __future__ import annotations

from services.extraction_prompts import (
    get_chunk_extraction_prompt,
    get_consolidation_prompt,
)


class TestGroundedPrompts:
    def test_chunk_prompt_requires_quotes(self):
        p = get_chunk_extraction_prompt(title="T", chunk_text="text", chunk_number=1, total_chunks=2)
        assert "quote" in p.lower()
        assert "verbatim" in p.lower()
        assert "defined_terms" in p

    def test_consolidation_prompt_preserves_quotes(self):
        p = get_consolidation_prompt(title="T", abstract="A", quick_extraction={},
                                     chunk_extractions=[{"key_findings": []}])
        assert "quote" in p.lower()

    def test_consolidation_corrections_section(self):
        p = get_consolidation_prompt(title="T", abstract="A", quick_extraction={},
                                     chunk_extractions=[], corrections="number 99.9 unmatched")
        assert "CORRECTIONS" in p and "99.9" in p

    def test_no_corrections_no_section(self):
        p = get_consolidation_prompt(title="T", abstract="A", quick_extraction={},
                                     chunk_extractions=[])
        assert "CORRECTIONS" not in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_extraction_prompts_grounding.py -q`
Expected: FAIL

- [ ] **Step 3: Update prompt templates**

In `CHUNK_EXTRACTION_PROMPT` (line 251), find the JSON schema section describing `key_findings` output and change findings to grounded objects. Add this block to the instructions (adapt wording to fit the template's existing style, keep `{chunk_text}` etc. placeholders intact):

```text
GROUNDING REQUIREMENT:
Every key finding and quantitative result MUST include a "quote" field containing a
VERBATIM excerpt (max 30 words) copied exactly from the chunk text that supports it.
Do not paraphrase inside "quote". If you cannot find a supporting quote, do not
report the finding.

Output key_findings as: [{"finding": "...", "quote": "..."}]
Also output defined_terms: an object mapping abbreviations/entities defined in this
chunk to their expansions, e.g. {"DEZ": "diethylzinc", "4-MP": "4-mercaptophenol"}.
```

In `CONSOLIDATION_PROMPT` (line 342), add to the instructions:

```text
Preserve the "quote" field of every key finding you keep, copied unchanged from the
chunk extraction it came from. key_findings in your output must be objects:
[{"finding": "...", "quote": "..."}].
{corrections_section}
```

Update `get_consolidation_prompt` signature and body:

```python
def get_consolidation_prompt(
    title: str,
    abstract: str,
    quick_extraction: dict,
    chunk_extractions: list[dict],
    journal: Optional[str] = None,
    authors: Optional[str] = None,
    year: Optional[int] = None,
    corrections: Optional[str] = None,
) -> str:
```

and pass:

```python
    corrections_section = ""
    if corrections:
        corrections_section = (
            "\nCORRECTIONS - a previous attempt failed verification. Fix these issues; "
            "only report values you can support with a verbatim quote:\n" + corrections
        )
    return CONSOLIDATION_PROMPT.format(
        ...existing kwargs...,
        corrections_section=corrections_section,
    )
```

- [ ] **Step 4: Run tests (new + existing prompt/extraction tests)**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_extraction_prompts_grounding.py tests/ -q -k "prompt or extraction"`
Expected: PASS (existing extraction tests must not break — the parser already passes dicts through)

- [ ] **Step 5: Commit**

```bash
git add src/services/extraction_prompts.py tests/unit/services/test_extraction_prompts_grounding.py
git commit -m "services: feat: Require grounding quotes and defined_terms in extraction prompts"
```

---

### Task 10: Wire ChunkProcessingState + fix num_ctx truncation

**Files:**
- Modify: `src/services/extraction_service.py:888-943` (extract_chunk), `:944-1110` (extract_deep), `:137-183` (ChunkProcessingState), `get_chunk_extraction_prompt` in `src/services/extraction_prompts.py:833`
- Test: `tests/unit/services/test_chunk_state.py` (new)

**Interfaces:**
- Consumes: `settings.ollama.chunk_num_ctx` / `consolidation_num_ctx` (Task 1); `ExtractionMetadata.extraction_checkpoint` (Task 2); `defined_terms` in chunk output (Task 9).
- Produces: `ChunkProcessingState.glossary: dict[str, str]`; `update_from_chunk(chunk_result: dict) -> None`; working `save_checkpoint()` / `load_checkpoint(paper_id)`; `extract_chunk(..., state: ChunkProcessingState | None = None)`; `get_chunk_extraction_prompt(..., prior_context: str = "")`. Consumed by Task 11/13 via extract_deep.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_chunk_state.py
"""Tests for ChunkProcessingState forward context (facts only) and checkpoints."""
from __future__ import annotations

from literature_core import get_session
from literature_core.models import ExtractionMetadata, Paper
from services.extraction_service import ChunkProcessingState


class TestForwardContext:
    def test_glossary_accumulates_from_chunk(self):
        state = ChunkProcessingState(paper_id=1)
        state.update_from_chunk({"defined_terms": {"DEZ": "diethylzinc"},
                                 "sections_in_chunk": ["Introduction"],
                                 "key_findings": [{"finding": "X", "quote": "X"}]})
        assert state.glossary == {"DEZ": "diethylzinc"}
        assert "Introduction" in state.sections_seen
        assert state.chunks_processed == 1

    def test_prompt_context_contains_facts_never_findings(self):
        state = ChunkProcessingState(paper_id=1)
        state.update_from_chunk({"defined_terms": {"DEZ": "diethylzinc"},
                                 "key_findings": [{"finding": "SECRET FINDING", "quote": "q"}]})
        ctx = state.to_prompt_context()
        assert "DEZ" in ctx and "diethylzinc" in ctx
        assert "SECRET FINDING" not in ctx  # findings are never forwarded


class TestCheckpoints:
    def test_save_and_load_roundtrip(self, db):
        with get_session() as s:
            p = Paper(title="T")
            s.add(p)
            s.flush()
            s.add(ExtractionMetadata(paper_id=p.id, extraction_method="test"))
            s.commit()
            pid = p.id
        state = ChunkProcessingState(paper_id=pid, chunks_processed=2,
                                     glossary={"ALD": "atomic layer deposition"})
        state.save_checkpoint()
        loaded = ChunkProcessingState.load_checkpoint(pid)
        assert loaded is not None
        assert loaded.chunks_processed == 2 and loaded.glossary["ALD"] == "atomic layer deposition"

    def test_load_missing_returns_none(self, db):
        assert ChunkProcessingState.load_checkpoint(999999) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_chunk_state.py -q`
Expected: FAIL (no glossary attribute / checkpoint returns None)

- [ ] **Step 3: Implement state wiring**

In `ChunkProcessingState` (extraction_service.py): add field `glossary: dict[str, str] = field(default_factory=dict)`; add:

```python
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
        from literature_core import get_session
        from literature_core.models import ExtractionMetadata
        with get_session() as session:
            meta = session.query(ExtractionMetadata).filter_by(paper_id=paper_id).first()
            if not meta or not meta.extraction_checkpoint:
                return None
            cp = meta.extraction_checkpoint
            return cls(paper_id=paper_id,
                       chunks_processed=cp.get("chunks_processed", 0),
                       sections_seen=cp.get("sections_seen", []),
                       glossary=cp.get("glossary", {}),
                       current_section=cp.get("current_section", "unknown"))
```

Extend `to_prompt_context()` to append glossary lines:

```python
        if self.glossary:
            terms = "; ".join(f"{k} = {v}" for k, v in sorted(self.glossary.items()))
            lines.append(f"Terms defined earlier in this paper: {terms}")
```

In `get_chunk_extraction_prompt`: add parameter `prior_context: str = ""`, inject into the template (add a `{prior_context}` placeholder near the top of `CHUNK_EXTRACTION_PROMPT` with a "Context from earlier chunks (facts only):" label; empty string when no context). Also instruct the model to output `sections_in_chunk: [..]`.

In `LLMClient.extract_chunk`: add parameter `state: ChunkProcessingState | None = None`; pass `prior_context=state.to_prompt_context() if state else ""`; change options to `"num_ctx": settings.ollama.chunk_num_ctx`.

In `extract_deep` pass 1 loop:

```python
        state = ChunkProcessingState.load_checkpoint(paper_id) or ChunkProcessingState(paper_id=paper_id)
        chunk_extractions = []
        for i, chunk_text in enumerate(chunks, 1):
            if i <= state.chunks_processed:
                continue  # crash recovery: already processed (results not cached - state only guides resume-count on same-session retry; full resume lands with the CLI runner)
            chunk_result = await self.extract_chunk(..., state=state)
            chunk_extractions.append(chunk_result)
            state.update_from_chunk(chunk_result)
            if state.paper_id:
                state.save_checkpoint()
```

Simplification note: chunk *results* aren't persisted, so a mid-paper crash restarts that paper's chunks from zero — the checkpoint's real job in Plan 1 is carrying glossary/sections forward and marking papers in-progress. Set `state.chunks_processed` comparison accordingly: reset the loaded state (`state.chunks_processed = 0`) at loop start but KEEP its glossary. Clear the checkpoint (set to `None`) after successful consolidation.

Consolidation call: change `"num_ctx": 8192` to `"num_ctx": settings.ollama.consolidation_num_ctx`, and before the POST add a truncation guard:

```python
        est_tokens = len(prompt) // 3
        if est_tokens > settings.ollama.consolidation_num_ctx:
            logger.warning("Consolidation prompt may exceed num_ctx",
                           extra={"paper_id": paper_id, "est_tokens": est_tokens,
                                  "num_ctx": settings.ollama.consolidation_num_ctx})
```

- [ ] **Step 4: Run tests**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_chunk_state.py tests/ -q -k "extraction or chunk"`
Expected: PASS (existing extraction tests unaffected — `state` is optional)

- [ ] **Step 5: Commit**

```bash
git add src/services/extraction_service.py src/services/extraction_prompts.py tests/unit/services/test_chunk_state.py
git commit -m "services: feat: Wire ChunkProcessingState (facts-only forward context), fix num_ctx truncation"
```

---

### Task 11: Extract-and-verify loop with corrective retry

**Files:**
- Modify: `src/services/verification_service.py`
- Test: `tests/unit/services/test_extract_and_verify.py` (new)

**Interfaces:**
- Consumes: `ExtractionService.extract_paper_deep(paper_id, ...)` (existing async classmethod), `VerificationService.verify_paper` (Task 8), `get_consolidation_prompt(corrections=...)` (Task 9).
- Produces: `async VerificationService.extract_and_verify(paper_id: int, extractor=None, minicheck=None, judge=None) -> dict` — runs deep extraction, verifies, and on `routing == "reextract"` re-runs deep extraction once passing `corrections="\n".join(failures)` through to consolidation, then re-verifies with `retried=True`. Returns the final verify_paper dict plus `"attempts": 1|2`. `ExtractionService.extract_paper_deep` gains a passthrough `corrections: str | None = None` parameter (threaded to `get_consolidation_prompt`). Consumed by Task 13.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/services/test_extract_and_verify.py
"""Tests for the auto re-extract-once loop (mocked extractor + verifier)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.verification_service import VerificationService


@pytest.mark.asyncio
class TestExtractAndVerify:
    async def test_accept_first_pass_no_retry(self):
        extractor = AsyncMock(return_value={"success": True})
        with patch.object(VerificationService, "verify_paper",
                          return_value={"score": 0.9, "routing": "accept", "failures": []}) as vp:
            result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["attempts"] == 1 and result["routing"] == "accept"
        extractor.assert_awaited_once()
        assert vp.call_count == 1

    async def test_borderline_retries_once_with_corrections(self):
        extractor = AsyncMock(return_value={"success": True})
        verdicts = [{"score": 0.7, "routing": "reextract", "failures": ["number unmatched: 99.9"]},
                    {"score": 0.88, "routing": "accept", "failures": []}]
        with patch.object(VerificationService, "verify_paper", side_effect=verdicts):
            result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["attempts"] == 2 and result["routing"] == "accept"
        assert extractor.await_count == 2
        # second extraction got the failure feedback
        assert "99.9" in extractor.await_args_list[1].kwargs["corrections"]

    async def test_still_bad_after_retry_goes_review(self):
        extractor = AsyncMock(return_value={"success": True})
        verdicts = [{"score": 0.7, "routing": "reextract", "failures": ["f"]},
                    {"score": 0.65, "routing": "review", "failures": ["f"]}]
        with patch.object(VerificationService, "verify_paper", side_effect=verdicts):
            result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["routing"] == "review" and result["attempts"] == 2

    async def test_failed_extraction_short_circuits(self):
        extractor = AsyncMock(return_value={"success": False, "error": "timeout"})
        result = await VerificationService.extract_and_verify(1, extractor=extractor)
        assert result["error"] == "timeout" and result["attempts"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_extract_and_verify.py -q`
Expected: FAIL (AttributeError: extract_and_verify)

- [ ] **Step 3: Implement the loop + corrections passthrough**

In `src/services/extraction_service.py`, add `corrections: Optional[str] = None` parameter to `extract_paper_deep` and `LLMClient.extract_deep`, threading it into `get_consolidation_prompt(...)`.

Add to `VerificationService`:

```python
    @classmethod
    async def extract_and_verify(cls, paper_id: int, extractor=None,
                                 minicheck: MiniCheckClient | None = None,
                                 judge: JudgeClient | None = None) -> dict:
        """Deep-extract then verify; auto re-extract once with corrective feedback."""
        from services.extraction_service import ExtractionService

        async def _default_extractor(pid: int, corrections: str | None = None) -> dict:
            extraction = await ExtractionService.extract_paper_deep(pid, corrections=corrections)
            if hasattr(extraction, "success"):
                return {"success": extraction.success, "error": getattr(extraction, "error", None)}
            return extraction

        extractor = extractor or _default_extractor

        first = await extractor(paper_id, corrections=None)
        if not first.get("success", False):
            return {"paper_id": paper_id, "error": first.get("error", "extraction failed"),
                    "attempts": 1}

        result = cls.verify_paper(paper_id, minicheck=minicheck, judge=judge, retried=False)
        if result.get("routing") != "reextract":
            return {**result, "attempts": 1}

        corrections = "\n".join(result.get("failures", []))
        logger.info("Re-extracting with corrections", extra={"paper_id": paper_id})
        second = await extractor(paper_id, corrections=corrections)
        if not second.get("success", False):
            return {**result, "attempts": 2, "routing": "review"}

        final = cls.verify_paper(paper_id, minicheck=minicheck, judge=judge, retried=True)
        return {**final, "attempts": 2}
```

(If `pytest-asyncio` is not already a dependency, check `environment.yml`; existing async service tests imply it is present — verify with `grep -r asyncio environment.yml tests/conftest.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/services/test_extract_and_verify.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/services/verification_service.py src/services/extraction_service.py tests/unit/services/test_extract_and_verify.py
git commit -m "services: feat: Add extract_and_verify loop with one corrective retry"
```

---

### Task 12: MCP tool — persisted scores + review queue

**Files:**
- Modify: `src/mcp_server/tools/extraction.py:186-217` (verify_extraction Tool schema), `:960-1030` (handlers)
- Test: `tests/integration/tools/test_verify_extraction_tool.py` (new)

**Interfaces:**
- Consumes: `VerificationService.verify_paper` (Task 8), `PaperContent.verification_score` (Task 2).
- Produces: `verify_extraction` tool with `scope` values `"paper"` (existing behavior, now backed by VerificationService and persisting), `"batch"` (existing), and new `"queue"` — returns papers with `verification_score < 0.85` ordered ascending, each with `paper_id, title, verification_score, routing, failures` from the stored `verification` JSON; `limit` parameter (default 20).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/tools/test_verify_extraction_tool.py
"""Integration tests for verify_extraction MCP tool queue scope."""
from __future__ import annotations

import json

import pytest

from literature_core import get_session
from literature_core.models import Paper, PaperContent
from mcp_server.tools import extraction as extraction_tools


@pytest.fixture
def scored_papers(db):
    with get_session() as s:
        for title, score, routing in [("Low paper", 0.4, "review"),
                                      ("Mid paper", 0.7, "review"),
                                      ("Good paper", 0.95, "accept")]:
            p = Paper(title=title)
            s.add(p)
            s.flush()
            s.add(PaperContent(paper_id=p.id, verification_score=score,
                               verification={"routing": routing, "failures": ["x"]}))
        s.commit()


@pytest.mark.asyncio
class TestVerifyQueue:
    async def test_queue_returns_low_scores_ascending(self, scored_papers):
        out = await extraction_tools.call_tool("verify_extraction", {"scope": "queue"})
        data = json.loads(out[0].text)
        titles = [p["title"] for p in data["data"]["papers"]]
        assert titles == ["Low paper", "Mid paper"]  # accept-tier paper excluded

    async def test_queue_respects_limit(self, scored_papers):
        out = await extraction_tools.call_tool("verify_extraction", {"scope": "queue", "limit": 1})
        data = json.loads(out[0].text)
        assert len(data["data"]["papers"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/integration/tools/test_verify_extraction_tool.py -q`
Expected: FAIL (unknown scope / wrong shape)

- [ ] **Step 3: Implement queue scope**

In the `verify_extraction` Tool schema (extraction.py:186-217): add `"queue"` to the `scope` enum and document it: "queue: list papers with verification_score below accept threshold, worst first". In the handler dispatch add:

```python
def _verification_queue(arguments: dict[str, Any]) -> list[TextContent]:
    from literature_core import get_session, success
    from literature_core.models import Paper, PaperContent
    from services.verification_service import VerificationService

    limit = int(arguments.get("limit", 20))
    with get_session() as session:
        rows = (
            session.query(Paper.id, Paper.title, PaperContent.verification_score,
                          PaperContent.verification)
            .join(PaperContent, PaperContent.paper_id == Paper.id)
            .filter(PaperContent.verification_score.isnot(None))
            .filter(PaperContent.verification_score < VerificationService.ACCEPT_THRESHOLD)
            .order_by(PaperContent.verification_score.asc())
            .limit(limit)
            .all()
        )
        papers = [{
            "paper_id": r.id, "title": r.title, "verification_score": r.verification_score,
            "routing": (r.verification or {}).get("routing"),
            "failures": (r.verification or {}).get("failures", []),
        } for r in rows]
    return [TextContent(type="text", text=json.dumps(success({"papers": papers,
                                                              "count": len(papers)})))]
```

Also switch the single-paper path (extraction.py:970) from `ExtractionService.verify_extraction(paper_id)` to `VerificationService.verify_paper(paper_id)` so scores persist. Keep `ExtractionService.verify_extraction` in place (other callers may use it) but its handler route now goes through the new service.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/integration/tools/test_verify_extraction_tool.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/mcp_server/tools/extraction.py tests/integration/tools/test_verify_extraction_tool.py
git commit -m "mcp: feat: Add verification review queue scope, persist scores via VerificationService"
```

---

### Task 13: CLI batch runner (backfill | extract | verify)

**Files:**
- Create: `src/scripts/enrich_pipeline.py`
- Test: `tests/unit/scripts/test_enrich_pipeline.py` (new)

**Interfaces:**
- Consumes: `VerificationService.extract_and_verify` (Task 11), `VerificationService.verify_paper` (Task 8), `ExtractionService.extract_pdf_and_store` + `get_papers_needing_extraction` (existing).
- Produces: `python -m scripts.enrich_pipeline --stage backfill|extract|verify|all [--limit N] [--paper-ids 1,2,3] [--dry-run]`. Pure planning functions for testability: `plan_backfill(session) -> list[int]` (papers with file_path but no chunks), `plan_extract(session, limit) -> list[int]` (papers with chunks whose extraction_depth != 'comprehensive' or content missing), `plan_verify(session, limit) -> list[int]` (comprehensive extractions with verification_score IS NULL). `run(argv) -> int` entry point printing a summary (processed/accepted/reextracted/review/errors).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/scripts/test_enrich_pipeline.py
"""Tests for enrich_pipeline stage planning and arg handling."""
from __future__ import annotations

from literature_core import get_session
from literature_core.models import (
    ExtractionMetadata, Paper, PaperChunk, PaperContent,
)
from scripts.enrich_pipeline import parse_args, plan_backfill, plan_extract, plan_verify


def _paper(s, title, file_path=None, chunked=False, depth=None, vscore=None):
    p = Paper(title=title, file_path=file_path)
    s.add(p)
    s.flush()
    if chunked:
        s.add(PaperChunk(paper_id=p.id, chunk_order=1, content="text",
                         word_count=1, char_count=4))
    if depth is not None or vscore is not None:
        s.add(PaperContent(paper_id=p.id, extraction_depth=depth,
                           verification_score=vscore))
    return p.id


class TestPlanning:
    def test_backfill_finds_pdf_without_chunks(self, db):
        with get_session() as s:
            stuck = _paper(s, "Stuck", file_path="/x/a.pdf", chunked=False)
            _paper(s, "Fine", file_path="/x/b.pdf", chunked=True)
            _paper(s, "NoPdf", file_path=None)
            s.commit()
            assert plan_backfill(s) == [stuck]

    def test_extract_finds_chunked_not_comprehensive(self, db):
        with get_session() as s:
            todo = _paper(s, "Abstract only", file_path="/x/a.pdf", chunked=True,
                          depth="abstract_only")
            _paper(s, "Done", file_path="/x/b.pdf", chunked=True, depth="comprehensive")
            s.commit()
            assert plan_extract(s, limit=10) == [todo]

    def test_verify_finds_unscored_comprehensive(self, db):
        with get_session() as s:
            todo = _paper(s, "Unscored", chunked=True, depth="comprehensive", vscore=None)
            _paper(s, "Scored", chunked=True, depth="comprehensive", vscore=0.9)
            s.commit()
            assert plan_verify(s, limit=10) == [todo]


class TestArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.stage == "all" and args.dry_run is False and args.limit is None

    def test_paper_ids_parsed(self):
        args = parse_args(["--stage", "verify", "--paper-ids", "3,5,8"])
        assert args.paper_ids == [3, 5, 8]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/scripts/test_enrich_pipeline.py -q`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Implement the runner**

```python
# src/scripts/enrich_pipeline.py
"""Enrichment batch runner - backfill chunks, deep-extract, verify.

Stage order matches the batch-by-model strategy (one Ollama model resident
per stage). Resumable: each planning query only selects papers not yet done,
so re-running after a crash continues where it left off.

Usage:
    cd src && mamba run -n litai python -m scripts.enrich_pipeline --stage all --limit 20
    cd src && mamba run -n litai python -m scripts.enrich_pipeline --stage verify --dry-run
    cd src && mamba run -n litai python -m scripts.enrich_pipeline --stage extract --paper-ids 12,99
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from literature_core import get_logger, get_session
from literature_core.models import Paper, PaperChunk, PaperContent

logger = get_logger(__name__)


def plan_backfill(session) -> list[int]:
    """Papers with a PDF on record but no chunks."""
    sub = session.query(PaperChunk.paper_id)
    rows = (session.query(Paper.id)
            .filter(Paper.file_path.isnot(None), Paper.file_path != "")
            .filter(~Paper.id.in_(sub))
            .order_by(Paper.id).all())
    return [r.id for r in rows]


def plan_extract(session, limit: int | None) -> list[int]:
    """Chunked papers lacking a comprehensive extraction."""
    sub = session.query(PaperChunk.paper_id)
    q = (session.query(Paper.id)
         .outerjoin(PaperContent, PaperContent.paper_id == Paper.id)
         .filter(Paper.id.in_(sub))
         .filter((PaperContent.extraction_depth.is_(None))
                 | (PaperContent.extraction_depth != "comprehensive"))
         .order_by(Paper.id))
    if limit:
        q = q.limit(limit)
    return [r.id for r in q.all()]


def plan_verify(session, limit: int | None) -> list[int]:
    """Comprehensive extractions never verified."""
    q = (session.query(Paper.id)
         .join(PaperContent, PaperContent.paper_id == Paper.id)
         .filter(PaperContent.extraction_depth == "comprehensive")
         .filter(PaperContent.verification_score.is_(None))
         .order_by(Paper.id))
    if limit:
        q = q.limit(limit)
    return [r.id for r in q.all()]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enrichment batch runner")
    p.add_argument("--stage", choices=["backfill", "extract", "verify", "all"], default="all")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--paper-ids", type=lambda s: [int(x) for x in s.split(",")], default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def _run_backfill(ids: list[int], dry_run: bool) -> dict:
    from services.extraction_service import ExtractionService
    stats = {"processed": 0, "errors": 0}
    for pid in ids:
        if dry_run:
            print(f"  [dry-run] would re-process PDF for paper {pid}")
            continue
        try:
            ExtractionService.extract_pdf_and_store(pid)
            stats["processed"] += 1
        except Exception as e:
            logger.error("Backfill failed", extra={"paper_id": pid, "error": str(e)})
            stats["errors"] += 1
    return stats


async def _run_extract_verify(ids: list[int], dry_run: bool) -> dict:
    from services.verification_service import VerificationService
    stats = {"processed": 0, "accepted": 0, "reextracted": 0, "review": 0, "errors": 0}
    for pid in ids:
        if dry_run:
            print(f"  [dry-run] would extract+verify paper {pid}")
            continue
        try:
            result = await VerificationService.extract_and_verify(pid)
            stats["processed"] += 1
            if result.get("error"):
                stats["errors"] += 1
            elif result.get("routing") == "accept":
                stats["accepted"] += 1
                if result.get("attempts", 1) > 1:
                    stats["reextracted"] += 1
            else:
                stats["review"] += 1
        except Exception as e:
            logger.error("Extract+verify failed", extra={"paper_id": pid, "error": str(e)})
            stats["errors"] += 1
        print(f"  paper {pid}: {stats}")
    return stats


def _run_verify_only(ids: list[int], dry_run: bool) -> dict:
    from services.verification_service import VerificationService
    stats = {"processed": 0, "accepted": 0, "review": 0, "errors": 0}
    for pid in ids:
        if dry_run:
            print(f"  [dry-run] would verify paper {pid}")
            continue
        try:
            result = VerificationService.verify_paper(pid)
            stats["processed"] += 1
            if result.get("error"):
                stats["errors"] += 1
            elif result.get("routing") == "accept":
                stats["accepted"] += 1
            else:
                stats["review"] += 1
        except Exception as e:
            logger.error("Verify failed", extra={"paper_id": pid, "error": str(e)})
            stats["errors"] += 1
    return stats


def run(argv: list[str]) -> int:
    args = parse_args(argv)
    with get_session() as session:
        stages = ["backfill", "extract", "verify"] if args.stage == "all" else [args.stage]
        for stage in stages:
            if args.paper_ids:
                ids = args.paper_ids
            elif stage == "backfill":
                ids = plan_backfill(session)
            elif stage == "extract":
                ids = plan_extract(session, args.limit)
            else:
                ids = plan_verify(session, args.limit)
            print(f"== Stage {stage}: {len(ids)} papers ==")
            if stage == "backfill":
                stats = _run_backfill(ids, args.dry_run)
            elif stage == "extract":
                stats = asyncio.run(_run_extract_verify(ids, args.dry_run))
            else:
                stats = _run_verify_only(ids, args.dry_run)
            print(f"== Stage {stage} done: {stats} ==")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
```

Note: `ExtractionService.extract_pdf_and_store(paper_id, force=False, ...)` (extraction_service.py:2032, confirmed) takes just `paper_id` — it fetches the paper and its `file_path` internally, so `_run_backfill` above calls it correctly with no path argument.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/unit/scripts/test_enrich_pipeline.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Smoke-test dry run against the real DB**

Run: `cd src && /home/dreece23/miniforge3/bin/mamba run -n litai python -m scripts.enrich_pipeline --stage all --limit 3 --dry-run`
Expected: three stage headers; backfill lists ~10 papers; no writes.

- [ ] **Step 6: Commit**

```bash
git add src/scripts/enrich_pipeline.py tests/unit/scripts/test_enrich_pipeline.py
git commit -m "scripts: feat: Add enrich_pipeline batch runner (backfill/extract/verify)"
```

---

### Task 14: Full suite, lint, docs

**Files:**
- Modify: `docs/TOOL_REFERENCE.md` (verify_extraction queue scope), `docs/WORKFLOWS.md` (enrichment batch workflow section), `CLAUDE.md` (add VerificationService to Key Services table; add enrich_pipeline to Development Commands)

- [ ] **Step 1: Run the full test suite**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m pytest tests/ -q`
Expected: all tests pass (fix regressions before proceeding — likely suspects: extraction tests touching prompts/signatures from Tasks 9–11)

- [ ] **Step 2: Lint**

Run: `/home/dreece23/miniforge3/bin/mamba run -n litai python -m flake8 src/`
Expected: clean

- [ ] **Step 3: Update docs**

- `CLAUDE.md` Key Services table: add row `| VerificationService | Tiered extraction verification (quotes, numbers, NLI, judge), scoring, review queue |`. Development Commands: add the enrich_pipeline usage line from Task 13's docstring.
- `docs/TOOL_REFERENCE.md`: document `verify_extraction` `scope: "queue"` with the response shape from Task 12.
- `docs/WORKFLOWS.md`: add "Enrichment batch (overnight)" section: pull models, `--stage all`, reading the review queue, thresholds (0.85/0.60) and calibration note (spot-check ~30–50 papers before trusting auto-accept).

- [ ] **Step 4: Commit**

```bash
git add docs/TOOL_REFERENCE.md docs/WORKFLOWS.md CLAUDE.md
git commit -m "docs: feat: Document verification pipeline, queue scope, and batch runner"
```
