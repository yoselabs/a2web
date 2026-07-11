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
- obstacle: optional, page-level failure mode (4 values); omitted on healthy pages.
- also_here: optional, the same-page index — query-grammar strings pointing at
  on-page content the answer did not surface; empty tuple omitted at the wire.
- other_pages: optional, off-page pointers (kind-tagged structural|drilldown);
  empty tuple omitted at the wire.

Closed-enum violations are rejected by the pydantic mirror at the seam; the
boundary type stays loose to keep the package independent of the typing layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OtherPageBoundary:
    """One off-page pointer (boundary side).

    Two provenance shapes:
    - `handle` set (the digest path) — the model referenced a `{{n}}` link
      handle; `url` is empty here and the domain seam rehydrates it from the
      closed link-digest set (dropping the entry if the handle is unknown).
    - `url` set (legacy) — the model emitted a URL it read in the content.
    `reason` is the model's justification (question-conditioned for a
    `drilldown`; ≤120 chars per prompt instruction; the pydantic mirror does not
    truncate). `kind` is `"drilldown"` (selection depends on the question) or
    `"structural"` (deterministic continuation — pagination, page-order); the
    boundary stays loose (any string) and the pydantic mirror validates the
    closed set. `off_domain` is filled by the domain seam after rehydration (the
    boundary layer has no page-URL context).
    """

    url: str
    reason: str
    kind: str = "drilldown"
    handle: int | None = None
    off_domain: bool = False


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
    Optional fields (`obstacle`, `also_here`, `other_pages`) default to
    None / empty tuple; the domain-side serializer omits them from the wire.
    """

    answer: str
    structural_form: str
    shape: str
    obstacle: str | None = None
    also_here: tuple[str, ...] = field(default_factory=tuple)
    other_pages: tuple[OtherPageBoundary, ...] = field(default_factory=tuple)
    # Dimensional refinement axes for a partial listing (content-aware
    # refinement guidance). Empty tuple omitted at the wire; the domain layer
    # additionally drops them unless the listing is confirmed partial.
    refinement_axes: tuple[RefinementAxisBoundary, ...] = field(default_factory=tuple)
    # The total item/result/comment count the model READ off the page,
    # language-agnostic (works where the regex count oracle's noun list does
    # not). Used at the domain seam as an oracle fallback for LLM-side
    # partialness detection. None when the page advertised no readable total.
    item_total_seen: int | None = None


__all__ = ["OtherPageBoundary", "RefinementAxisBoundary", "RouterPayload"]
