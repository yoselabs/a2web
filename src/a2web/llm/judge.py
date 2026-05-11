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
        criteria_lines = "\n".join(
            f"  {i + 1}. {c}" for i, c in enumerate(criteria)
        )
        user = JUDGE_V1.user_template.format(
            ask=task, content=criteria_lines, answer=answer
        )
        response = await self._provider.complete(
            system=JUDGE_V1.system,
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
        )

        parsed = _parse_verdict_json(response.text)
        try:
            scores = [int(s) for s in parsed["scores"]]
            overall = int(parsed["overall"])
            reached = bool(parsed["reached"])
            reasoning = str(parsed["reasoning"])
        except (KeyError, TypeError, ValueError) as exc:
            raise JudgeParseError(
                f"judge response missing required fields: {exc}",
                raw_text=response.text,
            ) from exc

        return JudgeVerdict(
            scores=scores,
            overall=overall,
            reached=reached,
            reasoning=reasoning,
            model=response.model,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
            raw={
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
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
