# Enrichment Pipeline Design: Extraction → Summarize → Verify → Search

**Date:** 2026-07-24
**Status:** Approved (pending implementation plan)
**Approach:** Extend existing pipeline (Approach A) — no parallel infrastructure

## Problem

The literature DB (601 papers) has strong extraction infrastructure but large coverage
and quality gaps:

| Gap | Count |
|---|---|
| Papers with PDF but no chunks | 10 (7 with `chunking_status='none'`) |
| Papers with no PDF at all | 128 |
| Papers with abstract-only extraction (no full-text summary) | 371 |
| Papers with populated `verification` column | 0 (column exists, never written) |
| Figures with images or AI analysis | 0 (4,271 caption-only rows) |
| Summaries/key findings covered by keyword search | 0 (FTS indexes title+abstract only) |

Constraints (user decisions, 2026-07-24):
- **Local Ollama only** — no cloud LLM costs; RTX 4070, 8 GB VRAM.
- **Full figure pipeline** — extract images + local VLM descriptions.
- **Verification policy** — auto re-extract once on low score, then human review queue.
- **PDF backup (Google Drive) deferred** — pipeline proceeds on local PDFs
  (all 473 attached PDFs resolve on disk; Drive sync never uploaded anything).

## Model configuration update

`src/config/ai_settings.py` defaults are stale (writer/triager still reference Qwen 1
tags). New defaults:

| Role | Setting | Model | Notes |
|---|---|---|---|
| Deep extractor + reader | `deep_extractor_model`, `reader_model` | `qwen3.5:9b` (~6.6 GB) | Best 8 GB-class model as of mid-2026; multimodal (text + image, 256K context) |
| Quick extractor | `quick_extractor_model` | `qwen3:4b-instruct-2507-q4_K_M` | ~2.5 GB |
| Vision (new) | `vision_model` | `qwen3.5:9b` (same model) | qwen3.5:9b accepts image input, so figure analysis reuses the resident deep extractor — no swap between extraction and figure phases. Fallback if its chart quality disappoints: `qwen3-vl:8b` |
| NLI verifier (new) | `verifier_model` | `bespoke-minicheck:7b` | SOTA grounded fact-checking (LLM-AggreFact); binary Yes/No per claim |
| Cross-family judge (new) | `judge_model` | `llama3.1:8b` | Borderline papers only; binary questions only |

VRAM rule: **batch by model, not by paper.** Generator, VLM, and verifier cannot be
co-resident in 8 GB; each pipeline stage runs across all target papers before the next
model loads (one ~15 s Ollama swap per stage, amortized).

## Verification design (research-backed)

Background research (2024–2026 literature; full citations at end) converged on:
fine-tuned small NLI checkers beat both QA-generation pipelines and same-model
LLM-as-judge at this scale; deterministic quote/number checks are the highest-yield
layer; SelfCheckGPT-style sampling (N=20) is not worth it when the source document is
available. Same-model rubric scoring is unreliable (self-preference bias); cross-family
binary checks are acceptable.

### Tiers (per paper)

1. **Tier 0 — deterministic (<1 s, CPU):**
   - Extraction schema requires, for every key finding / numeric field:
     `value + verbatim quote + location`.
   - Quote check: exact substring → longest contiguous numeric-token match → fuzzy
     sliding window (token overlap ≥ 0.85).
   - Number alignment: regex numbers from extracted fields, normalize (thousands
     separators, % vs fraction, scientific notation, rounding precision, units via
     `pint`), require a source counterpart. Unmatched number ⇒ hallucination flag.
   - Schema validation (types, ranges, enums) before any model-based scoring.
2. **Tier 1 — NLI faithfulness (~10–40 s):** split summary/findings into sentences;
   score each against its retrieved source chunks with `bespoke-minicheck:7b`
   (P(supported) per claim).
3. **Tier 2 — borderline papers only (score 0.60–0.85):**
   - k=3 self-consistency re-ask on disputed numeric fields (majority vote).
   - 3–4 binary cross-family judge questions (`llama3.1:8b`): main-finding coverage,
     no invented conclusions. Never numeric rubric scores.

### Composite score and routing

```
score = 0 if any hard gate fails, else
        0.45 * numeric_fidelity      # fraction of numbers/units/entities matched
      + 0.35 * claim_support         # mean MiniCheck P(supported)
      + 0.10 * quote_grounding       # fraction of grounding quotes matched ≥ 0.85
      + 0.10 * judge_pass            # binary spot-checks (1.0 if Tier 2 not needed)

Hard gates: schema-invalid; grounding quote missing/unmatched on a critical field;
            any critical number unmatched after one re-extraction.
```

**Critical fields** = numeric values in `key_findings` and `structured_data` (measured
quantities, sample sizes, performance figures). Non-critical = free-text fields
(`methodology_summary`, topics, paper_type), where an unmatched quote lowers the score
but does not hard-fail.

Routing: **≥ 0.85 accept** · **0.60–0.85 auto re-extract once** (failing spans/fields
fed back into a corrective prompt) · **< 0.60 after retry, or failed hard gate → review
queue**. Thresholds are starting points, to be recalibrated on ~30–50 hand-checked
papers. Expected: 70–85 % auto-accept; verification adds ~10–25 % to batch runtime.

### Persistence

- `paper_contents.verification` (existing JSON column, currently unused): full evidence —
  per-check results, failed claims/numbers, judge answers, model versions, timestamps.
- New indexed `paper_contents.verification_score` (float) via Alembic migration, so the
  review queue and search filters can query it.
- Review queue exposed through existing `verify_extraction` MCP tool with a new
  `scope: "queue"` (lowest scores first, with failure evidence).

## Pipeline phases

### Phase 1 — Backfill text/chunks
Re-run PDF processing (`extract_pdf_and_store`) for the 10 papers with a `file_path`
but no chunks. Produce an acquisition report for the 128 papers with no PDF
(future work: `find_open_access_pdf` + UW library links).

### Phase 2 — Grounded deep extraction (~371 papers)
- Extend deep-extraction prompt/schema with grounding quotes (see Tier 0).
- Keep the existing map → reduce shape (independent chunk extraction, then
  consolidation). Do NOT switch to sequential feed-forward of chunk summaries:
  research shows it propagates unverifiable errors forward and over-weights late
  chunks, and it breaks claim→chunk traceability that verification depends on.
- **Wire in `ChunkProcessingState`** (currently dead code — designed for forward
  context but never passed to chunk prompts; checkpoint methods are TODO stubs).
  Restrict its forwarded content to *factual structure only*: sections seen,
  document type, and a glossary of defined entities/abbreviations. Never forward
  findings or summaries. Implement the checkpoint save/load stubs for crash
  recovery during overnight batches.
- The reduce/consolidation prompt receives per-chunk findings **with their
  grounding quotes** (context-aware merging), so the final summary stays
  traceable to source text.
- **Fix `num_ctx` truncation risk:** chunk calls use `num_ctx=4096` and
  consolidation `8192`; Ollama silently truncates prompts beyond `num_ctx`, so
  many-chunk papers likely lose early-chunk findings in consolidation today.
  Raise limits for qwen3.5:9b (256K-capable; pick values within VRAM budget,
  e.g. 16–32K for consolidation) and log prompt token counts vs limit.
- Batch overnight via CLI runner; deep fields written to existing
  `paper_contents.deep_*` columns as today.

### Phase 3 — Verification
New `VerificationService` (`src/services/verification_service.py`) implementing the
tiers above. Stateless class methods, custom exceptions, response helpers, logging per
project conventions. `ExtractionService` calls it after each deep extraction; it can
also run standalone over existing extractions.

### Phase 4 — Figures and tables
- **Images:** PyMuPDF extracts embedded figure images to
  `data/figures/<paper_id>/fig_<n>.png`. Migration adds `image_path`,
  `vlm_description`, `vlm_model`, `analysis_date` to `paper_figures`.
- **VLM pass (`qwen3-vl:8b`):** descriptive tasks only — figure type, axes + units,
  legend entries, trend direction, relation to caption. Two-stage prompt (describe
  elements, then summarize), temperature 0, explicit "unanswerable" escape. VLMs are
  unreliable reading unmarked values off scientific charts (CharXiv: GPT-4o 47.1 % vs
  human 80.5 %), so any number the VLM emits is cross-checked against caption/body
  text by the Tier 0 matcher before storing; unverified numbers are dropped.
- **Tables:** text LLM extracts quantitative values from existing `paper_tables.markdown`
  into `paper_contents.structured_data`, quote-grounded and Tier 0-verified.
- Optional later upgrade: Docling for papers whose PyMuPDF table extraction is poor
  (better table structure, heavier runtime). Not in initial scope.

### Phase 5 — Search integration
- New contentless FTS5 table (`enrichment_fts`) in `literature_core/fts.py` over:
  `one_sentence_summary` (+deep), `key_findings`, `methodology_summary`, figure
  `vlm_description` + `caption`, table `caption` + `markdown`.
- `SearchService` fuses it into existing RRF ranking; results gain a `matched_in`
  field (`summary` / `figure` / `table` / `title_abstract`).
- Figure descriptions and table captions embedded into ChromaDB for semantic search
  (existing `EmbeddingService` patterns; graceful degradation if unavailable).

### Phase 6 — Batch CLI runner
`src/scripts/enrich_pipeline.py` (modeled on `zotero_import.py`):
- Stages: `backfill | extract | verify | figures | tables | index` (run one or all).
- Resumable (skips papers already current, keyed on `pdf_hash` + model version).
- `--limit`, `--paper-ids`, `--dry-run`; progress logging; end-of-run summary with
  counts (processed / accepted / re-extracted / queued for review).
- Stage order chosen so each Ollama model loads once per run.

## Error handling

- Ollama unreachable ⇒ fail fast with actionable message (existing `is_available()`
  pattern); partial batches resume cleanly.
- Per-paper failures logged and skipped, never abort the batch; failures surface in the
  end-of-run summary and `extraction_metadata` status fields.
- Verification failures are data, not errors — they route to re-extract/review queue.

## Testing

- Unit tests: `VerificationService` (deterministic tiers fully testable without
  models — quote matching, number normalization, composite scoring, routing), figure
  image extraction, FTS indexing/search fusion, CLI stage selection.
- Integration tests: `verify_extraction` queue scope, search `matched_in`, migration.
- LLM-dependent paths tested with mocked clients (existing `tests/fixtures/mocks.py`
  patterns).
- Threshold calibration: manual spot-check of ~30–50 papers via the review queue before
  trusting auto-accept.

## Out of scope (queued as future work)

- PDF backup (Google Drive/OneDrive) — deferred by user decision.
- Acquisition of the 128 missing PDFs (UW library links workflow).
- Retraction checking in `ValidationService`.
- PaperQA2-style cited-answer Q&A tool over verified chunks.
- RAGAS/DeepEval offline regression harness for prompt changes.

## Key research sources

MiniCheck ([arXiv 2404.10774](https://arxiv.org/abs/2404.10774),
[bespoke-minicheck on Ollama](https://ollama.com/library/bespoke-minicheck)) ·
Self-Preference Bias in LLM-as-a-Judge ([arXiv 2410.21819](https://arxiv.org/pdf/2410.21819)) ·
Panel-of-LLM-judges ([arXiv 2404.18796](https://arxiv.org/abs/2404.18796)) ·
Factored Verification ([arXiv 2310.10627](https://arxiv.org/pdf/2310.10627)) ·
PaperQA2 ([GitHub](https://github.com/future-house/paper-qa)) ·
Elicit extraction accuracy evaluations
([Cochrane comparison](https://onlinelibrary.wiley.com/doi/full/10.1002/cesm.70033)) ·
SelfCheckGPT ([OpenReview](https://openreview.net/forum?id=RwzFNbJ3Ez)) ·
Hierarchical merging for long-doc summarization ([arXiv 2502.00977](https://arxiv.org/pdf/2502.00977)) ·
CharXiv VLM chart benchmark ([site](https://charxiv.github.io/)) ·
Qwen2.5-VL report ([arXiv 2502.13923](https://arxiv.org/abs/2502.13923)) ·
Docling ([arXiv 2408.09869](https://arxiv.org/abs/2408.09869)) ·
Verification threshold selection ([arXiv 2412.12148](https://arxiv.org/pdf/2412.12148)) ·
2026 local-model rankings ([Morph](https://www.morphllm.com/best-ollama-models),
[InsiderLLM Qwen guide](https://insiderllm.com/guides/qwen-models-guide/),
[PromptQuorum vision models](https://www.promptquorum.com/power-local-llm/local-vision-models-llava-ollama-2026)).
