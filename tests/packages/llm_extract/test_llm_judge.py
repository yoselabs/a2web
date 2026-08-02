"""v0.4 step 2: Judge primitive tests.

Uses an in-process mock provider — no real API calls. Verifies:
- Happy-path scoring produces a populated JudgeVerdict.
- JSON parsing tolerates accidental markdown fences and prose wrappers.
- JudgeParseError fires on truly broken output with the raw text attached.
- Cost / token / model fields propagate through.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

from a2web.packages.llm_extract import (
    Judge,
    JudgeParseError,
    JudgeVerdict,
    ModelSpec,
    Provider,
    ProviderResponse,
)
from a2web.packages.llm_extract import judge as judge_mod
from a2web.packages.llm_extract.wobble import ParseError, WobblePolicy, WobbleTolerance
from tests._helpers.llm_doubles import DoubleArm


class _MockJudgeProvider:
    """Provider that returns a configured JSON string regardless of input."""

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT

    name = "mock"

    def __init__(self, *, text: str, cost_usd: float = 0.005) -> None:
        self.text = text
        self.cost_usd = cost_usd
        self.calls: list[dict] = []

    def available(self) -> bool:
        return True

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
    judge = Judge(provider=provider, model=ModelSpec("judge-model"))

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
    judge = Judge(provider=provider, model=ModelSpec("m"))

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
    judge = Judge(provider=provider, model=ModelSpec("m"))
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
    judge = Judge(provider=provider, model=ModelSpec("m"))
    verdict = await judge.score(task="?", criteria=["?"], answer="close-enough answer")
    assert verdict.overall == 4


@pytest.mark.asyncio
async def test_judge_raises_parse_error_on_garbage() -> None:
    """No JSON object in the response → JudgeParseError carrying raw text."""
    provider = _MockJudgeProvider(text="this is not JSON at all")
    judge = Judge(provider=provider, model=ModelSpec("m"))

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
    judge = Judge(provider=provider, model=ModelSpec("m"))
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
    judge = Judge(provider=provider, model=ModelSpec("m"))
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
    judge = Judge(provider=provider, model=ModelSpec("m"))
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
    judge = Judge(provider=provider, model=ModelSpec("m"))
    with pytest.raises(JudgeParseError):
        await judge.score(task="?", criteria=["c"], answer="x")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_overall", [[4, 5], {"v": 4}, "high", None])
async def test_judge_derive_survives_a_malformed_overall(bad_overall: object) -> None:
    """The two wobbles CO-OCCURRING: `reached` dropped AND `overall` unusable.

    Each was covered alone; their intersection was not, and it is the one input
    where the derive callable runs against a value nothing has validated. Live
    2026-08-02: a judge returned `overall` as a LIST, `_derive_reached` raised a
    bare `TypeError`, and it flew past the funnel's `ParseError` handler and the
    runner's per-cell `except JudgeParseError` to kill a 132-cell bench at cell
    24. The contract is that a judge whose output we cannot parse is an UNSCORED
    cell — so this must surface as `JudgeParseError`, the one type the runner
    isolates, and never as the raw coercion error.
    """
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [4], "overall": bad_overall, "reasoning": "x"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("m"))
    with pytest.raises(JudgeParseError) as caught:
        await judge.score(task="?", criteria=["c"], answer="x")
    # The raw text rides along — the runner writes it to judge_raw.txt, which is
    # the only forensic trail for a wobble that no longer crashes the run.
    assert "overall" in caught.value.raw_text


@pytest.mark.parametrize("bad_overall", [[4, 5], {"v": 4}, "high"])
def test_derive_reached_rejects_a_non_numeric_overall(bad_overall: object) -> None:
    """Pin the derive's OWN contract, not the funnel's net around it.

    The end-to-end test above stays green with this coercion reverted, because
    `_funnel_verdict`'s blanket clause converts the raw `TypeError` anyway — so
    it pins the net, never the typed guard. Calling the callable directly is the
    only way to tell the two fixes apart.
    """
    with pytest.raises(ParseError):
        judge_mod._derive_reached({"overall": bad_overall})


@pytest.mark.asyncio
async def test_judge_normalizes_any_policy_callable_failure() -> None:
    """A policy callable that raises something we did NOT anticipate is still a
    `JudgeParseError`, not a matrix-killer.

    Pins the blanket clause in `_funnel_verdict` directly rather than through
    the one derive that happens to exist today: narrowing it to the exceptions
    nameable now is exactly how the hole reopens for the next callable.
    """
    boom = WobblePolicy(
        WobbleTolerance.DERIVE,
        derive=lambda _parsed: (_ for _ in ()).throw(ZeroDivisionError("callable blew up")),
    )
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [4], "overall": 4, "reasoning": "x"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("m"))
    with (
        mock.patch.dict(judge_mod._JUDGE_POLICY, {"reached": boom}),
        pytest.raises(JudgeParseError, match="ZeroDivisionError"),
    ):
        await judge.score(task="?", criteria=["c"], answer="x")


@pytest.mark.asyncio
async def test_judge_missing_reasoning_now_defaults_to_empty() -> None:
    """`reasoning` is decorative — under the unified wobble discipline it
    DEFAULTs to "" rather than raising. The verdict still carries usable
    scores/overall/reached."""
    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5], "overall": 5, "reached": True}),
    )
    judge = Judge(provider=provider, model=ModelSpec("m"))
    verdict = await judge.score(task="?", criteria=["c"], answer="x")
    assert verdict.reasoning == ""
    assert verdict.overall == 5
    assert verdict.reached is True


@pytest.mark.asyncio
async def test_judge_reached_warning_log_emitted() -> None:
    """When `reached` is derived, a structured `llm_wobble` warning fires so
    operators can grep one key across all LLM-contract boundaries."""
    from tests._helpers.log_capture import capture_logs

    provider = _MockJudgeProvider(
        text=json.dumps({"scores": [5, 3, 5], "overall": 4, "reasoning": "ok"}),
    )
    judge = Judge(provider=provider, model=ModelSpec("test-model"))
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
    judge = Judge(provider=provider, model=ModelSpec("m"))
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


class _RaisingJudgeProvider:
    """Provider whose `complete()` fails loud with `AnyLLMError`."""

    DOUBLES_ARM = DoubleArm.OFF_CONTRACT

    name = "raising"

    def available(self) -> bool:
        return True

    async def complete(self, *, system, user, model, **_: object) -> ProviderResponse:
        from anyllm import AnyLLMError

        raise AnyLLMError("boom: provider down", retryable=True)


@pytest.mark.asyncio
async def test_judge_degrades_anyllm_error_to_parse_error() -> None:
    """AnyLLMError from the provider → empty verdict text → JudgeParseError.

    Mirrors the pre-adoption behavior: the old providers returned empty text on
    API failure and the funnel raised JudgeParseError. The AnyLLMError itself
    must NOT propagate out of `score()`.
    """
    judge = Judge(provider=_RaisingJudgeProvider(), model=ModelSpec("m"))
    with pytest.raises(JudgeParseError):
        await judge.score(task="Q", criteria=["A"], answer="ans")
