"""Central policy tables for the LLM-contract-parsing funnel.

Static policies live here. Policies that bind a per-field DERIVE callable
(e.g. `JUDGE_VERDICT_POLICY` referencing `_derive_reached`) live adjacent
to the callable in their consumer module.

**`OPTIONAL` vs `DEFAULT` is a claim about the prompt, and the prompt settles
it.** `DEFAULT` says "the contract asked for this and the model dropped it" and
fires an `llm_wobble`; `OPTIONAL` says "the contract permits its absence" and is
silent. Every field below is classified against what `prompts.py` literally
tells the model — `(required)` vs `(optional) ... OMIT` — not against how often
it happens to be present. Classifying an optional field `DEFAULT` is not a
harmless over-report: it fired five warnings on every healthy extraction, which
is how `llm_wobble` stopped being a signal at all.
"""

from __future__ import annotations

from llm_wobble import WobblePolicy, WobbleTolerance

# Extractor router-shape envelope (v0.21). Three required + three optional.
# The pydantic mirror at the seam (`fetcher_response._project_routing`) enforces
# closed-enum membership; this table only governs presence-recovery.
EXTRACTOR_ROUTING_POLICY: dict[str, WobblePolicy] = {
    # `answer` is the only true STRICT — without it, the envelope is unrecoverable.
    # structural_form / shape are DEFAULT-to-None so the funnel surfaces them
    # even when the model drops them; the `into` callable runs the
    # "answer kept, routing degraded" path locally instead of losing the answer
    # to a STRICT-raise inside the funnel.
    "answer": WobblePolicy(WobbleTolerance.STRICT),
    # prompt: "structural_form (required)" / "shape (required)". DEFAULT, not
    # OPTIONAL — dropping them IS the wobble, and it is the one this envelope
    # most needs reported: it is exactly the `unclassified` routing arm.
    "structural_form": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
    "shape": WobblePolicy(WobbleTolerance.DEFAULT, default=None),
    # The five the prompt marks "(optional)" and instructs the model to OMIT.
    # prompt: "obstacle (optional) ... OMIT on healthy pages" — so absence is
    # the healthy case, and the overwhelmingly common one.
    "obstacle": WobblePolicy(WobbleTolerance.OPTIONAL, default=None),
    # prompt: "also_here (optional)" / "other_pages (optional) ... If no
    # '## page links' list is present, OMIT other_pages". A page with nothing
    # to index legitimately supplies neither.
    "also_here": WobblePolicy(WobbleTolerance.OPTIONAL, default=()),
    "other_pages": WobblePolicy(WobbleTolerance.OPTIONAL, default=()),
    # prompt: "item_total_seen (optional) ... ONLY when structural_form=listing"
    # and "refinement_axes (optional) ... when structural_form=listing". Absent
    # on every non-listing page, which is most pages.
    "refinement_axes": WobblePolicy(WobbleTolerance.OPTIONAL, default=()),
    "item_total_seen": WobblePolicy(WobbleTolerance.OPTIONAL, default=None),
}

# Bench output-clarity axis. Score is load-bearing; reasoning is decorative —
# but "decorative" is not "optional": `bench_judge.py` asks for
# `{"clarity":<int 0-5>, "reasoning":"<one sentence>"}` unconditionally, so a
# missing `reasoning` is a model that ignored the contract. DEFAULT, and it
# stays rare enough to mean something.
BENCH_CLARITY_POLICY: dict[str, WobblePolicy] = {
    "clarity": WobblePolicy(WobbleTolerance.STRICT),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}

# Bench next_links-quality axis. Same shape, same reasoning as clarity above.
BENCH_NEXT_LINKS_POLICY: dict[str, WobblePolicy] = {
    "next_links_score": WobblePolicy(WobbleTolerance.STRICT),
    "reasoning": WobblePolicy(WobbleTolerance.DEFAULT, default=""),
}


__all__ = (
    "BENCH_CLARITY_POLICY",
    "BENCH_NEXT_LINKS_POLICY",
    "EXTRACTOR_ROUTING_POLICY",
)
