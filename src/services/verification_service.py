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
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

import httpx

from config.ai_settings import settings
from literature_core import PaperNotFoundError, get_logger, get_session
from literature_core.models import Paper, PaperContent

logger = get_logger(__name__)

FUZZY_THRESHOLD = 0.85
# 9B extractors paraphrase "quotes" rather than copying verbatim (reworded,
# de-hyphenated, sentence fragments joined). A quote whose content words are
# overwhelmingly present in the source is real grounding, not a fabrication;
# this fraction is the acceptance bar for the paraphrase fallback.
PARAPHRASE_THRESHOLD = 0.75

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?")

# bespoke-minicheck is trained for documents up to 32K tokens, but a 32K KV
# cache does not fit alongside the weights on an 8 GB GPU. Measured on an
# RTX 4070 Laptop (8188 MiB), one claim against a full-budget document:
#
#     num_ctx   VRAM     placement          time
#      8192     5.7 GB   100% GPU            7.5 s
#     16384     7.1 GB   12% CPU / 88% GPU  15.1 s
#     32768     9.3 GB   34% CPU / 66% GPU  52.6 s
#
# Spilling to CPU costs ~7x, so a claim is checked against several windows
# that stay resident instead of one document that does not. Whole-paper
# coverage is preserved: MAX_WINDOWS * WINDOW_CHARS still spans ~92K chars,
# and windows are tried best-match-first so a supported claim usually
# resolves on the first call. num_ctx must be set explicitly or Ollama
# silently truncates to the model default.
VERIFIER_NUM_CTX = 8192
VERIFIER_WINDOW_CHARS = 23000     # ~7.9K tokens of scientific text, leaves room for the claim
VERIFIER_WINDOW_OVERLAP = 1000    # so a sentence split by a boundary is still intact in one window
VERIFIER_MAX_WINDOWS = 4          # 4 x 23000 ~= the whole-paper budget this replaced
VERIFIER_DOC_CHAR_BUDGET = VERIFIER_WINDOW_CHARS * VERIFIER_MAX_WINDOWS


@dataclass
class QuoteMatch:
    """Result of matching a grounding quote against source text."""
    found: bool
    method: str          # "exact" | "numeric" | "fuzzy" | "paraphrase" | "none"
    score: float         # 0-1 match quality
    excerpt: str = ""    # matched source window (for evidence)


@dataclass
class NumberCheck:
    """One extracted number checked against source."""
    value: str           # as written in the claim
    matched: bool
    context: str = ""    # source window around the match


@dataclass
class ClaimSupport:
    """Tier 1 result, keeping "unsupported" and "could not check" distinct.

    Collapsing the two is what let an Ollama outage overwrite good extractions
    with plausible-looking low scores: every claim came back None, every None
    was counted as unsupported, and the composite landed in the review band
    with an empty failures list. `fraction` is therefore computed over claims
    that actually received a verdict.
    """
    fraction: float          # supported / checked (1.0 when there was nothing to check)
    evidence: list[dict]
    checked: int
    unchecked: int

    @property
    def verifier_down(self) -> bool:
        """True when claims existed but not one of them could be checked."""
        return self.checked == 0 and self.unchecked > 0


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
                    # Without an explicit num_ctx Ollama truncates the document to
                    # the model default, defeating whole-paper claim checking.
                    "options": {"temperature": 0.0, "num_predict": 4,
                                "num_ctx": VERIFIER_NUM_CTX},
                })
                if r.status_code != 200:
                    # Most often the model was never pulled (404). Silent Nones
                    # here are indistinguishable from a real "No", so say why.
                    logger.warning(
                        f"MiniCheck HTTP {r.status_code} from {self.host} "
                        f"for model {self.model}: {r.text[:200]}")
                    return None
                return r.json().get("response", "")
        except Exception as e:
            logger.warning(
                f"MiniCheck call failed ({type(e).__name__}: {e}) "
                f"host={self.host} model={self.model}")
            return None

    def check_claim(self, claim: str, document: str) -> bool | None:
        resp = self._generate(f"Document: {document}\nClaim: {claim}")
        if resp is None:
            return None
        return resp.strip().lower().startswith("yes")


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
                    logger.warning(
                        f"Judge HTTP {r.status_code} from {self.host} "
                        f"for model {self.model}: {r.text[:200]}")
                    return None
                return r.json().get("response", "").strip().lower().startswith("yes")
        except Exception as e:
            logger.warning(
                f"Judge call failed ({type(e).__name__}: {e}) "
                f"host={self.host} model={self.model}")
            return None


class VerificationService:
    """Stateless verification of extractions against source text."""

    ACCEPT_THRESHOLD = 0.85
    RETRY_THRESHOLD = 0.60

    W_NUMERIC, W_CLAIMS, W_QUOTES, W_JUDGE = 0.45, 0.35, 0.10, 0.10

    @staticmethod
    def _normalize(text: str) -> str:
        # Strip the literal quotation marks 9B models wrap quotes in, and remove
        # hyphens/dashes so "metal-organic" (model) matches "metalorganic"
        # (PDF-extracted source) and vice versa. Applied to both sides, so it
        # only ever makes matching more lenient symmetrically.
        text = re.sub(r"[\"'‘’“”«»]", "", text)
        text = re.sub(r"[-‐-―]", "", text)
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
                              excerpt=s_norm[max(0, idx - 50):idx + len(q_norm) + 50])

        nums = cls._numbers_in(quote)
        if nums and all(re.search(rf"(?<![\d.]){re.escape(n)}(?![\d.])", s_norm) for n in nums):
            m = re.search(rf"(?<![\d.]){re.escape(nums[0])}(?![\d.])", s_norm)
            first = m.start() if m else 0
            return QuoteMatch(found=True, method="numeric", score=0.9,
                              excerpt=s_norm[max(0, first - 100):first + 150])

        best, best_pos = 0.0, 0
        window = max(len(q_norm), 40)
        step = max(window // 4, 10)
        for pos in range(0, max(len(s_norm) - window // 2, 1), step):
            ratio = SequenceMatcher(None, q_norm, s_norm[pos:pos + window]).ratio()
            if ratio > best:
                best, best_pos = ratio, pos
        if best >= FUZZY_THRESHOLD:
            return QuoteMatch(found=True, method="fuzzy", score=round(best, 3),
                              excerpt=s_norm[best_pos:best_pos + window])

        # Paraphrase fallback: the model reworded the quote but it still reflects
        # real source content. Accept if the quote's content words (>=4 chars) are
        # overwhelmingly present in the source. A fabricated quote about content
        # not in the paper still fails this.
        content = set(re.findall(r"[a-z0-9]{4,}", q_norm))
        if content:
            src_words = set(re.findall(r"[a-z0-9]{4,}", s_norm))
            overlap = len(content & src_words) / len(content)
            if overlap >= PARAPHRASE_THRESHOLD:
                return QuoteMatch(found=True, method="paraphrase", score=round(overlap, 3))

        return QuoteMatch(found=False, method="none", score=round(best, 3))

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

    @staticmethod
    def _build_document(chunks: list[str]) -> str:
        """Concatenate chunks into one document up to the verifier's budget.

        MiniCheck is trained to judge a claim against a whole document, so we
        give it as much of the paper as fits rather than isolated fragments —
        essential for synthesized (review-level) findings that no single chunk
        states outright.
        """
        doc = ""
        for chunk in chunks:
            if len(doc) + len(chunk) > VERIFIER_DOC_CHAR_BUDGET:
                doc += chunk[:VERIFIER_DOC_CHAR_BUDGET - len(doc)]
                break
            doc += chunk + "\n"
        return doc

    @classmethod
    def _build_windows(cls, document: str, claim: str) -> list[str]:
        """Cut the document into VRAM-resident windows, best match for `claim` first.

        Ordering by word overlap means a claim stated plainly in one section
        is usually confirmed by the first call; only genuinely unsupported
        claims pay for the full sweep.
        """
        if len(document) <= VERIFIER_WINDOW_CHARS:
            return [document] if document else []

        step = VERIFIER_WINDOW_CHARS - VERIFIER_WINDOW_OVERLAP
        windows = [document[i:i + VERIFIER_WINDOW_CHARS]
                   for i in range(0, len(document), step)]
        windows = [w for w in windows if w.strip()]

        claim_words = set(re.findall(r"[a-z0-9]{4,}", claim.lower()))
        if claim_words:
            windows.sort(
                key=lambda w: len(claim_words & set(re.findall(r"[a-z0-9]{4,}", w.lower()))),
                reverse=True)
        return windows[:VERIFIER_MAX_WINDOWS]

    @classmethod
    def claim_support(cls, claims: list[str], chunks: list[str],
                      client: MiniCheckClient) -> ClaimSupport:
        """Fraction of claims supported by the paper, each checked against the
        full document (up to the verifier budget).

        A claim the verifier could not answer (None) is excluded from the
        denominator rather than counted against the extraction.
        """
        if not claims:
            return ClaimSupport(fraction=1.0, evidence=[], checked=0, unchecked=0)
        document = cls._build_document(chunks)
        evidence = []
        supported = checked = unchecked = 0
        for claim in claims:
            # Supported if ANY window supports it; unchecked only if EVERY
            # window failed to answer, so an outage stays distinguishable
            # from a claim the paper genuinely does not support.
            answered = found = False
            for window in cls._build_windows(document, claim):
                v = client.check_claim(claim, window)
                if v is None:
                    continue
                answered = True
                if v:
                    found = True
                    break
            verdict = found if answered else None
            if verdict is None:
                unchecked += 1
            else:
                checked += 1
                supported += bool(verdict)
            evidence.append({"claim": claim, "supported": verdict})
        return ClaimSupport(
            fraction=supported / checked if checked else 1.0,
            evidence=evidence, checked=checked, unchecked=unchecked)

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

    @classmethod
    def verify_paper(
        cls, paper_id: int, minicheck: MiniCheckClient | None = None,
        judge: JudgeClient | None = None, retried: bool = False,
    ) -> dict:
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

        # An extraction with nothing in it is a failed extraction, not a bad
        # one. Scoring it would produce a confident-looking number describing
        # an empty row, so refuse and surface an error. Deliberately NOT routed
        # to "reextract": the extraction just ran and returned nothing, so an
        # immediate blind retry would repeat it. `scripts.audit --fix`
        # (empty_extraction_marked_complete) requeues the row for the next
        # enrich_pipeline pass instead.
        if not summary and not findings:
            return {"paper_id": paper_id,
                    "error": "extraction is empty (no summary, no findings) - "
                             "run scripts.audit --fix to requeue it for re-extraction"}

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
        support = cls.claim_support(
            [t for t in claim_texts if t] + ([summary] if summary else []),
            chunks or [source], minicheck)

        # A score computed without the NLI verifier is not a verification
        # result. Persisting one overwrites good extractions with an artefact
        # of the outage, so abort before touching the row.
        if support.verifier_down:
            logger.error(
                "Verifier unavailable - refusing to persist a score",
                extra={"paper_id": paper_id, "claims_unchecked": support.unchecked},
            )
            return {
                "paper_id": paper_id,
                "error": (f"verifier unavailable: {support.unchecked} claim(s) could not be "
                          f"checked against {getattr(minicheck, 'model', 'the NLI verifier')}; "
                          f"nothing was persisted"),
            }

        claim_frac, claim_evidence = support.fraction, support.evidence
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
            "claims_unchecked": support.unchecked,
            "evidence": {"claims": claim_evidence, "judge": judge_answers},
        }

        with get_session() as session:
            content = session.query(PaperContent).filter_by(paper_id=paper_id).first()
            content.verification_score = score
            content.verification = {
                **result,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "retried": retried,
            }
            session.commit()

        logger.info(
            "Verified paper",
            extra={"paper_id": paper_id, "score": score, "routing": routing},
        )
        return result

    @classmethod
    async def extract_and_verify(cls, paper_id: int, extractor=None,
                                 minicheck: MiniCheckClient | None = None,
                                 judge: JudgeClient | None = None) -> dict:
        """Deep-extract then verify; auto re-extract once with corrective feedback."""
        from services.extraction_service import ExtractionService

        async def _default_extractor(pid: int, corrections: str | None = None) -> dict:
            extraction = await ExtractionService.extract_paper_deep(
                pid, corrections=corrections, force=corrections is not None)
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
