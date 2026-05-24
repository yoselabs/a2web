"""Boundary types for the affordances payload emitted by `request_affordances=True`.

These are package-side frozen dataclasses with string-typed fields — the
closed-enum `Literal` mirror lives on the domain side (`a2web.models`), and
projection happens at the seam in `fetcher_response.build_ask_response`.
Keeping the package surface free of pydantic + domain imports preserves the
`tests/test_packages_independence.py` invariant.

Shape comes from the v5 spike (V_CTX_V3 prompt):
  - page_kind: closed taxonomic label
  - page_kind_confidence: low | medium | high (epistemic about the label)
  - content_value: low | medium | high; None when page_kind is an obstacle
  - shapes: structural shapes present on the page (closed vocabulary)
  - follow_up_questions: questions the page can answer beyond the primary ask

Obstacle pages (page_kind in {paywalled, error, empty, blocked}) emit
content_value=None and empty tuples for shapes/follow_up_questions; the
domain-side serializer omits those fields from the wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AffordanceShape:
    """One structural shape present on the page (boundary side).

    `label` is intended to be one of the closed-vocabulary values
    {list, timeline, key-value, table, code, comments, citations, comparison};
    enforcement lives on the pydantic mirror, not here.
    """

    label: str
    where: str
    size: str


@dataclass(frozen=True, slots=True)
class AffordancesPayload:
    """The full affordances payload (boundary side).

    `page_kind_confidence` is independent of `content_value`: the model can be
    high-confidence the page is a 404 (page_kind="error") while content_value
    is None. See `eval/findings_2026-05-24-affordances-v5-two-axes.md` for the
    two-axis rubric rationale.
    """

    page_kind: str
    page_kind_confidence: str
    reasoning: str
    content_value: str | None = None
    shapes: tuple[AffordanceShape, ...] = field(default_factory=tuple)
    follow_up_questions: tuple[str, ...] = field(default_factory=tuple)


__all__ = ["AffordanceShape", "AffordancesPayload"]
