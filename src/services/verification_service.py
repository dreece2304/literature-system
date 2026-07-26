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

NUM_RE = re.compile(r"\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?")


@dataclass
class QuoteMatch:
    """Result of matching a grounding quote against source text."""
    found: bool
    method: str          # "exact" | "numeric" | "fuzzy" | "none"
    score: float         # 0-1 match quality
    excerpt: str = ""    # matched source window (for evidence)


@dataclass
class NumberCheck:
    """One extracted number checked against source."""
    value: str           # as written in the claim
    matched: bool
    context: str = ""    # source window around the match


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


class VerificationService:
    """Stateless verification of extractions against source text."""

    ACCEPT_THRESHOLD = 0.85
    RETRY_THRESHOLD = 0.60

    W_NUMERIC, W_CLAIMS, W_QUOTES, W_JUDGE = 0.45, 0.35, 0.10, 0.10

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
