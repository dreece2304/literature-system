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
        # Q3 ("does the summary contain conclusions absent from the source?") has
        # pass_verdict=False, so an all-pass run answers False there, True elsewhere.
        client = FakeJudge([True, True, False])
        score, answers = VerificationService.judge_pass("sum", ["f1"], "abs", client)
        assert score == 1.0 and len(answers) == 3

    def test_invented_conclusion_fails(self):
        # Q3 asks "does the summary contain conclusions absent from the source?"
        # judge answering True there = invented conclusion = fail for that question
        client = FakeJudge([True, True, True])
        score, _ = VerificationService.judge_pass("sum", ["f1"], "abs", client)
        assert score < 1.0

    def test_none_counts_as_pass_fail_open(self):
        client = FakeJudge([None, None, None])
        score, answers = VerificationService.judge_pass("sum", ["f1"], "abs", client)
        assert score == 1.0
        assert all(a["verdict"] is None for a in answers)
