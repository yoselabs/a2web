"""LLM-as-judge primitive.

Used by the eval suite to blind-score system answers against per-question
criteria. Also reusable for any future quality gate that needs a model
verdict (e.g. "is this answer good enough to cache?").

Structurally it's an `Extractor` over the `JUDGE_V1` template, plus a JSON
parse on the output. Cost, tokens, and latency come from Extractor for
free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .extractor import ModelSpec
from .prompts import JUDGE_V1
from .providers.base import Provider
from .wobble import (
    ParseError,
    WobblePolicy,
    WobbleTolerance,
    parse_with_policy,
    recovered_fields,
    unwrap,
)

# Threshold for deriving `reached` from `overall` when the model drops the
# field. Matches the aggregation in `src/a2web/llm_eval/report.py` which
# treats overall >= 3 as a "reached" verdict for reach-rate stats.
_REACHED_DERIVED_THRESHOLD: int = 3


def _derive_reached(parsed: dict[str, Any]) -> bool:
    """Compute `reached` from `overall` against the report-side threshold.

    Used as the DERIVE-policy callable for the `reached` field. The judge
    parser separately validates that `overall` is present and an int via
    the STRICT-policy path, so this derive runs only after `overall` is
    known-good.
    """
    return int(parsed["overall"]) >= _REACHED_DERIVED_THRESHOLD


# Per-field policy table for the judge boundary. STRICT fields are
# load-bearing (an unparseable verdict has no signal to salvage); DERIVE
# fields recover from a known-derivable peer; DEFAULT fields are decorative.
_JUDGE_POLICY: dict[str, WobblePolicy] = {
    "scores": WobblePolicy(WobbleTolerance.STRICT),
    "overall": WobblePolicy(WobbleTolerance.STRICT),
    "reached": WobblePolicy(WobbleTolerance.DERIVE, derive=_derive_reached),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}


class JudgeParseError(ValueError):
    """Raised when the judge's response cannot be parsed as JSON.

    Carries the raw text on `.raw_text` so callers can log it for debugging
    instead of fighting the format every retry.
    """

    def __init__(self, message: str, raw_text: str) -> None:
        super().__init__(message)
        self.raw_text = raw_text


@dataclass(slots=True)
class JudgeVerdict:
    """One judge verdict over (task, criteria, answer)."""

    scores: list[int]
    overall: int
    reached: bool
    reasoning: str
    model: str
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: dict[str, Any] | None = field(default=None)


# Permissive object extractor — when the funnel's strict json.loads fails on
# the raw response, this regex pulls the first balanced-looking object out of
# mixed prose for a second funnel attempt.
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(frozen=True, slots=True)
class _ParsedJudgeFields:
    """Funnel `into` payload — provider-side fields (cost / latency / model)
    are joined back in by the caller."""

    scores: list[int]
    overall: int
    reached: bool
    reasoning: str


def _build_judge_fields(parsed: dict[str, Any]) -> _ParsedJudgeFields:
    """Funnel `into` callable. Funnel guarantees STRICT fields are present
    and runs the DERIVE/DEFAULT path for `reached`/`reasoning`; we coerce
    int / bool / str here and surface coercion failures as ParseError."""
    try:
        scores = [int(s) for s in parsed["scores"]]
        overall = int(parsed["overall"])
    except (TypeError, ValueError) as exc:
        raise ParseError(f"judge: int coercion failed: {exc}") from exc
    return _ParsedJudgeFields(
        scores=scores,
        overall=overall,
        reached=bool(parsed["reached"]),
        reasoning=str(parsed["reasoning"]),
    )


class Judge:
    """Score an answer against criteria with an LLM. Uses JUDGE_V1.

    Usage:
        # provider is resolved upstream and injected (see Extractor docstring).
        judge = Judge(provider=provider,
                      model=ModelSpec("claude-sonnet-4-6"))
        verdict = await judge.score(
            task="Who designed Rust?",
            criteria=["names Graydon Hoare", "mentions Mozilla / 2006"],
            answer="Rust was created by Graydon Hoare at Mozilla.",
        )
    """

    def __init__(
        self,
        *,
        provider: Provider,
        model: ModelSpec,
        max_tokens: int = 512,
    ) -> None:
        # Judge needs JUDGE_V1 specifically and builds its user message by
        # hand (3 placeholders — ask / content / answer — don't fit
        # Extractor's 2-slot abstraction). Provider held directly.
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> ModelSpec:
        return self._model

    async def score(
        self,
        *,
        task: str,
        criteria: list[str],
        answer: str,
    ) -> JudgeVerdict:
        """Run the judge over (task, criteria, answer). Raises JudgeParseError
        on un-parseable output."""
        criteria_lines = "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(criteria))
        user = JUDGE_V1.user_template.format(ask=task, content=criteria_lines, answer=answer)
        response = await self._provider.complete(
            system=JUDGE_V1.system,
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
        )

        wobbled = _funnel_verdict(response.text, model=self._model.model)
        fields: _ParsedJudgeFields = unwrap(wobbled)

        raw: dict[str, Any] = {
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        }
        if "reached" in recovered_fields(wobbled):
            raw["reached_derived"] = True

        return JudgeVerdict(
            scores=fields.scores,
            overall=fields.overall,
            reached=fields.reached,
            reasoning=fields.reasoning,
            model=response.model,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            raw=raw,
        )


def _funnel_verdict(text: str, *, model: str) -> Any:
    """Funnel the judge response: try the strict path first (fences + JSON);
    on ParseError fall back to a permissive first-{...} regex extraction and
    re-funnel that substring. Raises JudgeParseError if neither yields a
    valid object."""
    try:
        return parse_with_policy(
            text,
            policies=_JUDGE_POLICY,
            into=_build_judge_fields,
            boundary="judge",
            model=model,
        )
    except ParseError:
        pass

    match = _OBJECT_RE.search(text)
    if match is None:
        raise JudgeParseError("no JSON object found in judge response", raw_text=text)
    try:
        return parse_with_policy(
            match.group(0),
            policies=_JUDGE_POLICY,
            into=_build_judge_fields,
            boundary="judge",
            model=model,
        )
    except ParseError as exc:
        raise JudgeParseError(
            f"judge response: {exc}",
            raw_text=text,
        ) from exc


__all__ = ["Judge", "JudgeParseError", "JudgeVerdict"]
