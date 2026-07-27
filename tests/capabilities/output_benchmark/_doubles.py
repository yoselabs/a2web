"""Canned judges shared by the output-benchmark capability tests.

These bypass the provider entirely — the tests they serve are about the
harness's bookkeeping (which axis ran, what it recorded, what the report says),
never about judge quality.

Deliberately NOT a stub *system*: a fake system that hand-builds its envelope is
what let the ADR-0015 rename pass unnoticed, because the fake wrote whatever key
the reader read. Envelope-shaped doubles belong next to the test that owns their
shape, built from the production model — see `test_axis_disposition.py`.
"""

from __future__ import annotations

from a2web.llm_eval import BenchJudge, ClarityVerdict, NextLinksVerdict
from a2web.packages.llm_extract import Judge, JudgeVerdict, ModelSpec


class MockJudge(Judge):
    """Quality judge with a canned verdict."""

    def __init__(self) -> None:
        self._model = ModelSpec("judge-mock")
        self._max_tokens = 512

    async def score(self, *, task: str, criteria: list[str], answer: str) -> JudgeVerdict:
        return JudgeVerdict(
            scores=[4] * len(criteria),
            overall=4,
            reached=True,
            reasoning="mock",
            model="judge-mock",
        )


class MockBenchJudge(BenchJudge):
    """Bench judge with canned clarity and next_links verdicts."""

    def __init__(self) -> None:
        self._model = ModelSpec("bench-mock")
        self._max_tokens = 256

    async def score_clarity(self, *, task: str, answer: str) -> ClarityVerdict:
        return ClarityVerdict(score=4, reasoning="mock clarity", model="bench-mock")

    async def score_next_links(self, *, task: str, next_links: str) -> NextLinksVerdict:
        return NextLinksVerdict(score=3, reasoning="mock next_links", model="bench-mock")


__all__ = ["MockBenchJudge", "MockJudge"]
