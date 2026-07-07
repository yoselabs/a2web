"""Central policy tables for the LLM-contract-parsing funnel.

Static policies live here. Policies that bind a per-field DERIVE callable
(e.g. `JUDGE_VERDICT_POLICY` referencing `_derive_reached`) live adjacent
to the callable in their consumer module.
"""

from __future__ import annotations

from ._internal import WobblePolicy, WobbleTolerance

# Extractor router-shape envelope (v0.21). Three required + four optional.
# The pydantic mirror at the seam (`fetcher_response._project_routing`) enforces
# closed-enum membership; this table only governs presence-recovery.
EXTRACTOR_ROUTING_POLICY: dict[str, WobblePolicy] = {
    # `answer` is the only true STRICT — without it, the envelope is unrecoverable.
    # structural_form / shape are DEFAULT-to-None so the funnel surfaces them
    # even when the model drops them; the `into` callable runs the
    # "answer kept, routing degraded" path locally instead of losing the answer
    # to a STRICT-raise inside the funnel.
    "answer": WobblePolicy(WobbleTolerance.STRICT),
    "structural_form": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
    "shape": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
    "genre": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
    "obstacle": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
    "ask_here": WobblePolicy(WobbleTolerance.DEFAULT, default=()),
    "try_url": WobblePolicy(WobbleTolerance.DEFAULT, default=()),
    # Content-aware refinement guidance — both optional; the model omits them on
    # non-partial / non-listing pages, so DEFAULT-recover to empty / None.
    "refinement_axes": WobblePolicy(WobbleTolerance.DEFAULT, default=()),
    "item_total_seen": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
}

# Bench output-clarity axis. Score is load-bearing; reasoning is decorative.
BENCH_CLARITY_POLICY: dict[str, WobblePolicy] = {
    "clarity": WobblePolicy(WobbleTolerance.STRICT),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}

# Bench next_links-quality axis. Same shape as clarity.
BENCH_NEXT_LINKS_POLICY: dict[str, WobblePolicy] = {
    "next_links_score": WobblePolicy(WobbleTolerance.STRICT),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}


__all__ = (
    "BENCH_CLARITY_POLICY",
    "BENCH_NEXT_LINKS_POLICY",
    "EXTRACTOR_ROUTING_POLICY",
)
