"""v0.4 step 2: Judge primitive tests.

Uses an in-process mock provider — no real API calls. Verifies:
- Happy-path scoring produces a populated JudgeVerdict.
- JSON parsing tolerates accidental markdown fences and prose wrappers.
- JudgeParseError fires on truly broken output with the raw text attached.
- Cost / token / model fields propagate through.
"""

from __future__ import annotations

import json

import pytest

from a2web.packages.llm_extract import (
    Judge,
    JudgeParseError,
    JudgeVerdict,
    ModelSpec,
    Provider,
    ProviderResponse,
)


class _MockJudgeProvider:
    """Provider that returns a configured JSON string regardless of input."""

    name = "mock"

    def __init__(self, *, text: str, cost_usd: float = 0.005) -> None:
        self.text = text
        self.cost_usd = cost_usd
        self.calls: list[dict] = []

    async def complete(
        self,
        *,
        system,
        user,
        model,
        max_tokens=1024,
        temperature=0.0,
        thinking_disabled=True,
    ) -> ProviderResponse:
        self.calls.append({"system": system, "user": user, "model": model})
        return ProviderResponse(
            text=self.text,
            model=model,
            prompt_tokens=200,
            completion_tokens=40,
            cost_usd=self.cost_usd,
            latency_ms=350,
        )


def test_mock_judge_provider_satisfies_provider_protocol() -> None:
    assert isinstance(_MockJudgeProvider(text="{}"), Provider)


@pytest.mark.asyncio
async def test_judge_scores_correct_answer_high() -> None:
    """Happy path: well-formed JSON → populated JudgeVerdict."""
    provider = _MockJudgeProvider(
        text=json.dumps(
            {
                "scores": [5, 5],
                "overall": 5,
                "reached": True,
                "reasoning": "names Hoare + Mozilla + year",
            }
        ),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "judge-model"))

    verdict = await judge.score(
        task="Who designed Rust?",
        criteria=["names Graydon Hoare", "mentions Mozilla / 2006"],
        answer="Rust was designed by Graydon Hoare at Mozilla, ~2006.",
    )

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.scores == [5, 5]
    assert verdict.overall == 5
    assert verdict.reached is True
    assert "Hoare" in verdict.reasoning
    assert verdict.model == "judge-model"
    assert verdict.cost_usd == pytest.approx(0.005)
    assert verdict.latency_ms == 350


@pytest.mark.asyncio
async def test_judge_records_failure_answer_as_not_reached() -> None:
    """A 'fetch failed' answer should round-trip reached=False through the
    judge response back into the verdict."""
    provider = _MockJudgeProvider(
        text=json.dumps(
            {
                "scores": [0, 0],
                "overall": 0,
                "reached": False,
                "reasoning": "HTTP 404",
            }
        ),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))

    verdict = await judge.score(
        task="Who designed Rust?",
        criteria=["names Graydon Hoare", "mentions Mozilla / 2006"],
        answer="The server returned HTTP 404.",
    )
    assert verdict.reached is False
    assert verdict.overall == 0


@pytest.mark.asyncio
async def test_judge_tolerates_markdown_fence() -> None:
    """Models sometimes wrap JSON in ```json fences despite STRICT instructions."""
    provider = _MockJudgeProvider(
        text=("```json\n" + json.dumps({"scores": [3], "overall": 3, "reached": True, "reasoning": "partial"}) + "\n```"),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    verdict = await judge.score(task="?", criteria=["?"], answer="partial answer")
    assert verdict.overall == 3
    assert verdict.scores == [3]


@pytest.mark.asyncio
async def test_judge_tolerates_prose_wrapper() -> None:
    """Models sometimes emit a sentence before the JSON object."""
    provider = _MockJudgeProvider(
        text=(
            "Here is my verdict: " + json.dumps({"scores": [4], "overall": 4, "reached": True, "reasoning": "close enough"}) + " — done."
        ),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    verdict = await judge.score(task="?", criteria=["?"], answer="close-enough answer")
    assert verdict.overall == 4


@pytest.mark.asyncio
async def test_judge_raises_parse_error_on_garbage() -> None:
    """No JSON object in the response → JudgeParseError carrying raw text."""
    provider = _MockJudgeProvider(text="this is not JSON at all")
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))

    with pytest.raises(JudgeParseError) as ei:
        await judge.score(task="?", criteria=["?"], answer="x")
    assert ei.value.raw_text == "this is not JSON at all"


@pytest.mark.asyncio
async def test_judge_derives_reached_when_missing() -> None:
    """The wikipedia-rust v0.23 bench-failure shape — model omits `reached`
    but returns a fully-scored verdict. Derive `reached` from `overall`
    against the report-side threshold rather than discarding the signal."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5, 3, 5], "overall": 4, "reasoning": "good"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    verdict = await judge.score(task="?", criteria=["c"], answer="x")
    assert verdict.reached is True
    assert verdict.raw is not None
    assert verdict.raw.get("reached_derived") is True


@pytest.mark.asyncio
async def test_judge_derives_reached_when_null() -> None:
    """Explicit null on `reached` is the same wobble — derive from overall."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [1, 0], "overall": 1, "reached": None, "reasoning": "miss"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    verdict = await judge.score(task="?", criteria=["c"], answer="x")
    assert verdict.reached is False
    assert verdict.raw is not None
    assert verdict.raw.get("reached_derived") is True


@pytest.mark.asyncio
async def test_judge_explicit_reached_does_not_set_derived_flag() -> None:
    """When the model returns `reached` explicitly, the raw dict carries
    no `reached_derived` key — distinguishes recovered from authoritative."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5], "overall": 5, "reached": True, "reasoning": "ok"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    verdict = await judge.score(task="?", criteria=["c"], answer="x")
    assert verdict.reached is True
    assert verdict.raw is not None
    assert "reached_derived" not in verdict.raw


@pytest.mark.asyncio
async def test_judge_missing_overall_still_raises() -> None:
    """`overall` is not derivable — its absence is a hard failure."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5], "reasoning": "x"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    with pytest.raises(JudgeParseError):
        await judge.score(task="?", criteria=["c"], answer="x")


@pytest.mark.asyncio
async def test_judge_missing_reasoning_now_defaults_to_empty() -> None:
    """`reasoning` is decorative — under the unified wobble discipline it
    DEFAULTs to "" rather than raising. The verdict still carries usable
    scores/overall/reached."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5], "overall": 5, "reached": True}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    verdict = await judge.score(task="?", criteria=["c"], answer="x")
    assert verdict.reasoning == ""
    assert verdict.overall == 5
    assert verdict.reached is True


@pytest.mark.asyncio
async def test_judge_reached_warning_log_emitted() -> None:
    """When `reached` is derived, a structured `llm_wobble` warning fires so
    operators can grep one key across all LLM-contract boundaries."""
    from structlog.testing import capture_logs

    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5, 3, 5], "overall": 4, "reasoning": "ok"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "test-model"))
    with capture_logs() as logs:
        await judge.score(task="?", criteria=["c"], answer="x")
    warnings = [r for r in logs if r.get("event") == "llm_wobble" and r.get("field") == "reached"]
    assert len(warnings) == 1
    assert warnings[0]["boundary"] == "judge"
    assert warnings[0]["tolerance"] == "derive"
    assert warnings[0]["model"] == "test-model"


@pytest.mark.asyncio
async def test_judge_sends_criteria_and_answer_into_template() -> None:
    """The constructed user message embeds the criteria + answer."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5], "overall": 5, "reached": True, "reasoning": "ok"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("mock", "m"))
    await judge.score(
        task="Specific task",
        criteria=["Criterion A", "Criterion B"],
        answer="The Specific Answer",
    )
    assert len(provider.calls) == 1
    user_payload = provider.calls[0]["user"]
    assert "Specific task" in user_payload
    assert "Criterion A" in user_payload
    assert "Criterion B" in user_payload
    assert "The Specific Answer" in user_payload
    assert "STRICT JSON ONLY" in user_payload  # template guardrail survives


def test_judge_parse_error_carries_raw_text() -> None:
    """JudgeParseError exposes .raw_text for caller logging."""
    err = JudgeParseError("bad", raw_text="<<garbage>>")
    assert err.raw_text == "<<garbage>>"
    assert "bad" in str(err)
