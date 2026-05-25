"""Benchmark-local LLM judge axes — output clarity + next_links quality.

The product judge (`a2web.packages.llm_extract.Judge`) scores answer quality
against per-question criteria. The benchmark needs two further LLM-judged
axes that are not product concerns:

  - **output clarity** — how cleanly a downstream agent can act on the output
    directly, without re-parsing chrome, hedging, or duplicated content.
  - **next_links quality** — for listing pages, whether the curated
    "what to fetch next" candidates are the right set for the task.

These templates live in the benchmark, not in the product `prompts.py`, so
the product judge surface stays minimal. Like the product judge, scoring is
blind (the judge is not told which system produced the output).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..packages.llm_extract import (
    JudgeParseError,
    ModelSpec,
    Provider,
    WobblePolicy,
    WobbleTolerance,
    apply_policy,
)

# Per-field wobble policies for the two bench-judge surfaces. Score fields are
# STRICT (no signal to salvage if the scoring number is gone); reasoning is
# decorative — DEFAULTs to "" so a dropped field doesn't fail the axis.
_CLARITY_POLICY: dict[str, WobblePolicy] = {
    "clarity": WobblePolicy(WobbleTolerance.STRICT),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}
_NEXT_LINKS_POLICY: dict[str, WobblePolicy] = {
    "next_links_score": WobblePolicy(WobbleTolerance.STRICT),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}

_CLARITY_TEMPLATE = (
    "You are a strict, blind judge assessing OUTPUT CLARITY — how cleanly a "
    "downstream AI agent can act on a tool's output without re-parsing noise. "
    "You do NOT know which system produced this output.\n\n"
    "A clear output is direct, well-structured, free of boilerplate, and "
    "ready to use as-is. A noisy output buries the answer under chrome, "
    "hedging, navigation text, or duplicated content.\n\n"
    "TASK THE OUTPUT WAS PRODUCED FOR: {task}\n\n"
    "OUTPUT TO JUDGE:\n{answer}\n\n"
    "Score clarity 0-5 (0=unusable noise, 3=usable with effort, 5=immediately "
    "actionable). Respond with STRICT JSON ONLY, no prose, no markdown fence:\n"
    '{{"clarity":<int 0-5>, "reasoning":"<one sentence>"}}'
)

_NEXT_LINKS_TEMPLATE = (
    "You are a strict, blind judge assessing whether a set of suggested "
    '"what to fetch next" links is the RIGHT set for a research task on a '
    "listing / index page. You do NOT know which system produced them.\n\n"
    "Good next_links point to the items a researcher would actually drill "
    "into for the task — not navigation, ads, login links, or unrelated "
    "pages. Reward relevance and coverage; penalize chrome and omissions. "
    "You cannot verify external facts and neither can the harness — judge "
    "the set's structure, relevance, and coverage for the task; never "
    "penalize an entry for being unfamiliar or assume it is fabricated.\n\n"
    "TASK: {task}\n\n"
    "SUGGESTED NEXT LINKS:\n{next_links}\n\n"
    "Score 0-5 (0=wrong/empty set, 3=partially right, 5=exactly the set a "
    "researcher wants). Respond with STRICT JSON ONLY, no prose, no fence:\n"
    '{{"next_links_score":<int 0-5>, "reasoning":"<one sentence>"}}'
)

_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


@dataclass(slots=True)
class ClarityVerdict:
    """One output-clarity verdict."""

    score: int
    reasoning: str
    model: str
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass(slots=True)
class NextLinksVerdict:
    """One next_links-quality verdict."""

    score: int
    reasoning: str
    model: str
    cost_usd: float = 0.0
    latency_ms: int = 0


class BenchJudge:
    """Scores the benchmark-only clarity and next_links axes via an LLM.

    Holds a `Provider` directly — each axis has a single-template, three-slot
    user message that does not fit the product `Extractor`'s abstraction.
    """

    def __init__(
        self,
        *,
        provider: Provider,
        model: ModelSpec,
        max_tokens: int = 256,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_tokens = max_tokens

    @property
    def model(self) -> ModelSpec:
        return self._model

    async def score_clarity(self, *, task: str, answer: str) -> ClarityVerdict:
        """Score how cleanly an agent can act on `answer`. Raises
        JudgeParseError on un-parseable output."""
        user = _CLARITY_TEMPLATE.format(task=task, answer=answer)
        response = await self._provider.complete(
            system=(),
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
        )
        parsed = _parse_json(response.text)
        try:
            score = int(
                apply_policy(
                    parsed,
                    "clarity",
                    _CLARITY_POLICY["clarity"],
                    boundary="bench_judge_clarity",
                    model=self._model.model,
                    raw_excerpt=response.text,
                )
            )
            reasoning = str(
                apply_policy(
                    parsed,
                    "reasoning",
                    _CLARITY_POLICY["reasoning"],
                    boundary="bench_judge_clarity",
                    model=self._model.model,
                    raw_excerpt=response.text,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise JudgeParseError(
                f"clarity verdict missing required fields: {exc}",
                raw_text=response.text,
            ) from exc
        return ClarityVerdict(
            score=score,
            reasoning=reasoning,
            model=response.model,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
        )

    async def score_next_links(self, *, task: str, next_links: str) -> NextLinksVerdict:
        """Score whether `next_links` (a rendered block) is the right "what to
        fetch next" set for `task`. Raises JudgeParseError on bad output."""
        user = _NEXT_LINKS_TEMPLATE.format(task=task, next_links=next_links)
        response = await self._provider.complete(
            system=(),
            user=user,
            model=self._model.model,
            max_tokens=self._max_tokens,
            thinking_disabled=True,
        )
        parsed = _parse_json(response.text)
        try:
            score = int(
                apply_policy(
                    parsed,
                    "next_links_score",
                    _NEXT_LINKS_POLICY["next_links_score"],
                    boundary="bench_judge_next_links",
                    model=self._model.model,
                    raw_excerpt=response.text,
                )
            )
            reasoning = str(
                apply_policy(
                    parsed,
                    "reasoning",
                    _NEXT_LINKS_POLICY["reasoning"],
                    boundary="bench_judge_next_links",
                    model=self._model.model,
                    raw_excerpt=response.text,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise JudgeParseError(
                f"next_links verdict missing required fields: {exc}",
                raw_text=response.text,
            ) from exc
        return NextLinksVerdict(
            score=score,
            reasoning=reasoning,
            model=response.model,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
        )


def _parse_json(text: str) -> dict[str, Any]:
    """Strict JSON first, then a permissive first-object regex. Raises
    JudgeParseError if neither yields an object."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = _OBJECT_RE.search(text)
    if match is None:
        raise JudgeParseError("no JSON object found in bench-judge response", raw_text=text)
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"bench-judge object is not valid JSON: {exc}", raw_text=text) from exc


__all__ = ["BenchJudge", "ClarityVerdict", "NextLinksVerdict"]
