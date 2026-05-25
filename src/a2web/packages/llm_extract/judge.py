"""LLM-as-judge primitive.

Used by the eval suite to blind-score system answers against per-question
criteria. Also reusable for any future quality gate that needs a model
verdict (e.g. "is this answer good enough to cache?").

Structurally it's an `Extractor` over the `JUDGE_V1` template, plus a JSON
parse on the output. Cost, tokens, and latency come from Extractor for
free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .extractor import ModelSpec
from .prompts import JUDGE_V1
from .providers.base import Provider
from .wobble import WobblePolicy, WobbleTolerance, apply_policy

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


# Permissive object extractor — strict json.loads first, then this regex
# pulls the first balanced-looking object out of mixed prose.
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


class Judge:
    """Score an answer against criteria with an LLM. Uses JUDGE_V1.

    Usage:
        judge = Judge(provider=AnthropicProvider(),
                      model=ModelSpec("anthropic", "claude-sonnet-4-6"))
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

        parsed = _parse_verdict_json(response.text)

        # STRICT fields — `scores` and `overall`. Wrap KeyError/TypeError from
        # `apply_policy` (and the int-coercion below) in JudgeParseError so
        # the runner's existing `judge_failed` path keeps working.
        try:
            scores_raw = apply_policy(
                parsed,
                "scores",
                _JUDGE_POLICY["scores"],
                boundary="judge",
                model=self._model.model,
                raw_excerpt=response.text,
            )
            scores = [int(s) for s in scores_raw]
            overall = int(
                apply_policy(
                    parsed,
                    "overall",
                    _JUDGE_POLICY["overall"],
                    boundary="judge",
                    model=self._model.model,
                    raw_excerpt=response.text,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise JudgeParseError(
                f"judge response missing required fields: {exc}",
                raw_text=response.text,
            ) from exc

        # `reached` (DERIVE) and `reasoning` (DEFAULT) — wobble-tolerant.
        # The reached-derive path always runs once `overall` is in scope; the
        # `apply_policy` call uses the `_derive_reached` callable above.
        reached_present_before = "reached" in parsed and parsed["reached"] is not None
        reached = bool(
            apply_policy(
                parsed,
                "reached",
                _JUDGE_POLICY["reached"],
                boundary="judge",
                model=self._model.model,
                raw_excerpt=response.text,
            )
        )
        reasoning = str(
            apply_policy(
                parsed,
                "reasoning",
                _JUDGE_POLICY["reasoning"],
                boundary="judge",
                model=self._model.model,
                raw_excerpt=response.text,
            )
        )

        raw: dict[str, Any] = {
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        }
        if not reached_present_before:
            raw["reached_derived"] = True

        return JudgeVerdict(
            scores=scores,
            overall=overall,
            reached=reached,
            reasoning=reasoning,
            model=response.model,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            raw=raw,
        )


def _parse_verdict_json(text: str) -> dict[str, Any]:
    """Parse a judge response: try strict JSON first, then a permissive
    first-object regex. Raise JudgeParseError if neither works."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Strip an accidental markdown fence — happens occasionally even
        # though the template says STRICT JSON ONLY.
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```\s*$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = _OBJECT_RE.search(text)
    if match is None:
        raise JudgeParseError("no JSON object found in judge response", raw_text=text)
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(
            f"first object substring is not valid JSON: {exc}",
            raw_text=text,
        ) from exc


__all__ = ["Judge", "JudgeParseError", "JudgeVerdict"]
