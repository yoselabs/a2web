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

import re
from dataclasses import dataclass
from typing import Any

from ..packages.llm_extract import JudgeParseError, ModelSpec, Provider
from ..packages.llm_extract.wobble import (
    BENCH_CLARITY_POLICY,
    BENCH_NEXT_LINKS_POLICY,
    ParseError,
    parse_with_policy,
    unwrap,
)

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
        wobbled = _funnel_two_field(
            response.text,
            score_field="clarity",
            boundary="bench_judge_clarity",
            policies=BENCH_CLARITY_POLICY,
            model=self._model.model,
        )
        fields = unwrap(wobbled)
        return ClarityVerdict(
            score=fields["score"],
            reasoning=fields["reasoning"],
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
        wobbled = _funnel_two_field(
            response.text,
            score_field="next_links_score",
            boundary="bench_judge_next_links",
            policies=BENCH_NEXT_LINKS_POLICY,
            model=self._model.model,
        )
        fields = unwrap(wobbled)
        return NextLinksVerdict(
            score=fields["score"],
            reasoning=fields["reasoning"],
            model=response.model,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
        )


def _funnel_two_field(
    text: str,
    *,
    score_field: str,
    boundary: str,
    policies: dict[str, Any],
    model: str,
) -> Any:
    """Funnel a `{score_field: int, reasoning: str}` envelope through wobble.

    Try the strict-fence path first; on ParseError fall back to extracting the
    first `{...}` substring (the model occasionally wraps prose around the
    JSON despite the prompt). Raises JudgeParseError if neither yields a
    valid object.
    """

    def _build(parsed: dict[str, Any]) -> dict[str, Any]:
        try:
            score = int(parsed[score_field])
        except (TypeError, ValueError, KeyError) as exc:
            raise ParseError(f"{boundary}: int coercion failed: {exc}") from exc
        return {"score": score, "reasoning": str(parsed["reasoning"])}

    try:
        return parse_with_policy(
            text, policies=policies, into=_build, boundary=boundary, model=model
        )
    except ParseError:
        pass

    match = _OBJECT_RE.search(text)
    if match is None:
        raise JudgeParseError(f"no JSON object found in {boundary} response", raw_text=text)
    try:
        return parse_with_policy(
            match.group(0), policies=policies, into=_build, boundary=boundary, model=model
        )
    except ParseError as exc:
        raise JudgeParseError(f"{boundary}: {exc}", raw_text=text) from exc


__all__ = ["BenchJudge", "ClarityVerdict", "NextLinksVerdict"]
