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

from anyllm.errors import AnyLLMError

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

#: Scores the SET's shape, never the merit of the individual items.
#:
#: The previous wording said "reward relevance and coverage; penalize chrome and
#: omissions", and in practice the judge read that as an invitation to grade each
#: entry on whether it was a worthwhile thing to have linked. Measured on
#: 2026-08-01 (`eval/runs/2026-08-01_152218`), `gh-trending-best` was marked down
#: to 3 for "pollut[ing] coverage with clearly off-topic entries like
#: SimplifyJobs/Summer2027-Internships (an internship list, not a repo to adopt)
#: and paperswithbacktest/awesome-systematic-trading (a curated list, not a
#: project)".
#:
#: Both of those were on GitHub trending that day. a2web relayed them, which is
#: exactly what ADR-0012 requires — a2web shapes and relays, it never ranks,
#: filters, hides, or crowns by a criterion of its own. **So the axis was
#: rewarding editorial filtering that the product forbids**, and a system that
#: obeyed ADR-0012 could not score full marks. The scores also moved with
#: whatever happened to trend overnight rather than with any change to a2web.
#:
#: On verification, and why the "do not assume fabrication" clause SURVIVES the
#: rewrite rather than being inverted as `close-guards-that-read-green` §6.5
#: proposed. That task's premise is "once it can verify" — but the judge is
#: handed the task string and the rendered block, and nothing else. It has no
#: page, so it genuinely cannot check whether a URL was on it. Telling a blind
#: judge to suspect fabrication buys guesses, not verification.
#:
#: ADR-0014 is a DETERMINISTIC property — every emitted URL traceable to an
#: anchor on the fetched page — and belongs in a check that can actually read the
#: page, not in an LLM's opinion. Left for that decision rather than papered over
#: here; §6.5 stays open with this reasoning attached.
_NEXT_LINKS_TEMPLATE = (
    "You are a strict, blind judge assessing whether a set of suggested "
    '"what to fetch next" links is the RIGHT SET for a research task on a '
    "listing / index page. You do NOT know which system produced them.\n\n"
    "WHAT YOU ARE JUDGING — the composition of the set:\n"
    "- Are these the page's drill-down targets (the items the listing lists), "
    "rather than chrome: navigation, ads, login, footer, share links, "
    "pagination?\n"
    "- Is the coverage sensible for the task — enough of the page's items to "
    "work from, without obvious duplication?\n"
    "- Do the `kind`, `reason` and `anchor` columns describe each entry "
    "honestly and informatively?\n\n"
    "WHAT YOU ARE NOT JUDGING — read this carefully, it is the common mistake:\n"
    "- NOT whether each linked item is individually worthwhile, on-trend, "
    "high-quality, or the one you would pick. The system is REQUIRED to relay "
    "what the page listed, faithfully and without filtering or ranking. An "
    "entry you consider uninteresting, off-topic, or a poor choice is NOT a "
    "defect if the page listed it — penalising it would reward editorial "
    "filtering the system is forbidden to do.\n"
    "- NOT whether the set matches what that page shows TODAY. You cannot see "
    "the page, and its contents change.\n"
    "- NOT whether a URL exists. You cannot verify external facts and neither "
    "can this prompt. Never penalise an entry for being unfamiliar and never "
    "assume it is fabricated; existence is checked elsewhere.\n\n"
    "TASK: {task}\n\n"
    "SUGGESTED NEXT LINKS:\n{next_links}\n\n"
    "Score 0-5 on the SET's composition (0 = wrong or empty set, or mostly "
    "chrome; 3 = the right kind of set with real gaps or noticeable chrome; "
    "5 = cleanly the page's drill-down targets, well described, well covered). "
    "Respond with STRICT JSON ONLY, no prose, no fence:\n"
    '{{"next_links_score":<int 0-5>, "reasoning":"<one sentence>"}}'
)

_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _degraded_note(axis: str, exc: AnyLLMError) -> str:
    """Reasoning text for a cell whose judge could not be reached.

    Scored 0 and SAID SO, rather than crashing the run or silently omitting the
    cell. A bench that dies on one provider hiccup loses the other 41 entries;
    a bench that quietly drops the cell reports a mean over a set nobody chose.

    Neither existed before 2026-08-01: `bench_judge` was the one `complete()`
    site with no `except AnyLLMError`, so the per-request timeout added the same
    day propagated straight out of `asyncio.gather` and killed the whole run.
    Its siblings (`Extractor.extract`, `Judge.score`) had the degrade seam all
    along — wrapping the provider covered the CALL everywhere, which is not the
    same as handling the FAILURE everywhere.
    """
    return f"JUDGE UNAVAILABLE ({axis}): {exc}. Scored 0 — this is a bench-infrastructure failure, NOT a quality signal about the answer."


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
        JudgeParseError on un-parseable output.

        A provider failure degrades THIS CELL rather than the run — see
        `_degraded_note`.
        """
        user = _CLARITY_TEMPLATE.format(task=task, answer=answer)
        try:
            response = await self._provider.complete(
                system=(),
                user=user,
                model=self._model.model,
                max_tokens=self._max_tokens,
                thinking_disabled=True,
            )
        except AnyLLMError as exc:
            return ClarityVerdict(score=0, reasoning=_degraded_note("clarity", exc), model=self._model.model)
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
        fetch next" set for `task`. Raises JudgeParseError on bad output.

        A provider failure degrades THIS CELL rather than the run.
        """
        user = _NEXT_LINKS_TEMPLATE.format(task=task, next_links=next_links)
        try:
            response = await self._provider.complete(
                system=(),
                user=user,
                model=self._model.model,
                max_tokens=self._max_tokens,
                thinking_disabled=True,
            )
        except AnyLLMError as exc:
            return NextLinksVerdict(score=0, reasoning=_degraded_note("next_links", exc), model=self._model.model)
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
        return parse_with_policy(text, policies=policies, into=_build, boundary=boundary, model=model)
    except ParseError:
        pass

    match = _OBJECT_RE.search(text)
    if match is None:
        raise JudgeParseError(f"no JSON object found in {boundary} response", raw_text=text)
    try:
        return parse_with_policy(match.group(0), policies=policies, into=_build, boundary=boundary, model=model)
    except ParseError as exc:
        raise JudgeParseError(f"{boundary}: {exc}", raw_text=text) from exc


__all__ = ["BenchJudge", "ClarityVerdict", "NextLinksVerdict"]
