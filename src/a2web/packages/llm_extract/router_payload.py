"""Boundary types for the router-shape payload emitted by `request_routing=True`.

Package-side frozen dataclasses with string-typed fields — the closed-enum
`Literal` mirror lives on the domain side (`a2web.models`), and projection
happens at the seam in `fetcher_response.build_response`. Keeping the package
surface free of pydantic + domain imports preserves the
`tests/test_packages_independence.py` invariant.

Shape comes from `eval/spikes/surface_eval_v2.py` (the pre-impl validation
eval; findings in `eval/findings_2026-05-25-router-shape-pre-impl.md`):

- answer: required, the model's concise answer to the question.
- structural_form: required, one of 9 closed values — what the page IS.
- shape: required, one of 7 closed values — the data shape of the content.
- genre: optional, what the page is ABOUT (7 values); omitted when none applies.
- obstacle: optional, page-level failure mode (4 values); omitted on healthy pages.
- ask_here: optional, same-URL follow-up questions; empty tuple omitted at the wire.
- try_url: optional, different-URL drilldowns; empty tuple omitted at the wire.

Closed-enum violations are rejected by the pydantic mirror at the seam; the
boundary type stays loose to keep the package independent of the typing layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NextUrlBoundary:
    """One curated drilldown URL (boundary side).

    `url` MUST appear verbatim in the page content sent to the model; this
    invariant is enforced by validation at the domain seam, not here.
    `reason` is the model's question-conditioned justification (≤120 chars
    per prompt instruction; the pydantic mirror does not truncate).
    """

    url: str
    reason: str


@dataclass(frozen=True, slots=True)
class RefinementAxisBoundary:
    """One dimensional refinement axis for a partial listing (boundary side).

    A *dimension* to re-query on (e.g. "brand", "price floor", "sort order"),
    never a specific value drawn from the retrieved (possibly biased) sample.
    `how` is the model's one-line guidance on applying that dimension. The
    dimensional-not-value discipline is a prompt instruction; the boundary type
    stays loose (any string) and the domain seam does not truncate.
    """

    dimension: str
    how: str


@dataclass(frozen=True, slots=True)
class RouterPayload:
    """The full router-shape payload (boundary side).

    Required fields (`answer`, `structural_form`, `shape`) MUST be populated;
    the parser returns None for the whole payload when any is missing.
    Optional fields (`genre`, `obstacle`, `ask_here`, `try_url`) default to
    None / empty tuple; the domain-side serializer omits them from the wire.
    """

    answer: str
    structural_form: str
    shape: str
    genre: str | None = None
    obstacle: str | None = None
    ask_here: tuple[str, ...] = field(default_factory=tuple)
    try_url: tuple[NextUrlBoundary, ...] = field(default_factory=tuple)
    # Dimensional refinement axes for a partial listing (content-aware
    # refinement guidance). Empty tuple omitted at the wire; the domain layer
    # additionally drops them unless the listing is confirmed partial.
    refinement_axes: tuple[RefinementAxisBoundary, ...] = field(default_factory=tuple)
    # The total item/result/comment count the model READ off the page,
    # language-agnostic (works where the regex count oracle's noun list does
    # not). Used at the domain seam as an oracle fallback for LLM-side
    # partialness detection. None when the page advertised no readable total.
    item_total_seen: int | None = None


__all__ = ["NextUrlBoundary", "RefinementAxisBoundary", "RouterPayload"]
