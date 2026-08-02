"""Is this ALL of it?

The question ADR-0015 exists to answer, and the one that had no name anywhere
in the codebase until this file.
"""

from __future__ import annotations

from ... import content_expectations
from ...listing_oracle import listing_has_more, listing_oracle
from ..context import FetchContext


def _phase_listing_completeness(fc: FetchContext, *, raw_html: str) -> None:
    """Sufficiency check — is a fetched listing complete, or a truncated sample?

    Runs after record extraction (listing-completeness Slice 1). When the page
    is a listing (`fc.record_count` set by `_escalate_via_records`) and an item
    oracle (the advertised total) exceeds the parsed record count beyond
    tolerance, surface an honest `listing_partial` signal plus the structured
    `items_loaded`/`items_total` counts — so the caller can never mistake an
    infinite-scroll sample for the whole listing (ADR-0009 on the sufficiency
    axis). Pure verdict — no fetching; the bounded scroll-to-complete action is
    a later slice.

    Silent when: the page is not a listing (`record_count is None`); the count
    meets the oracle within tolerance (`assess` → `ready`); or there is neither
    a numeric oracle nor a structural "more exists" affordance. A
    positive-oracle/zero-record `fail` is the presence axis — left to the
    obstacle/wall machinery.

    Two evidence paths, numeric-first: a quantified oracle drives the exact
    `listing_partial` signal (`items_loaded` + `items_total`); absent a count, a
    pagination / infinite-scroll affordance drives the unquantified
    `listing_more` fallback (`items_loaded` set, `items_total` unknown). The
    numeric oracle is authoritative — when present, the structural affordance is
    ignored (a leftover "next" on a complete last page is not a truncation).
    """
    if fc.record_count is None:
        return
    total = listing_oracle(raw_html)
    if total is not None:
        # Record the regex oracle even on a complete verdict — the LLM-side
        # fallback consults this to stay a strict superset (never overrides).
        fc.regex_oracle_total = total
        if content_expectations.assess(loaded=fc.record_count, total=total) != "partial":
            # Symmetric CLEAR, not an early return. This runs after every
            # escalation now, so the second pass is the one that matters: a
            # scroll render that completed the listing must retract the
            # `listing_partial` signal, and a function that can only ever SET it
            # would report a truncation that has since been resolved. The clear
            # was previously hand-written inside `_phase_listing_render`, which
            # is where it had to live when there was no loop head to return to.
            fc.items_loaded = None
            fc.items_total = None
            fc.items_more = False
            return
        # Flag the partial state; the `listing_partial` hint is appended by
        # `build_response` from these fields.
        fc.items_loaded = fc.record_count
        fc.items_total = total
        fc.items_more = False
        return
    # No numeric oracle — fall back to the structural affordance. `items_total`
    # stays None (unknown); `build_response` emits `listing_more` off `items_more`.
    if listing_has_more(raw_html):
        fc.items_loaded = fc.record_count
        fc.items_more = True


def _apply_llm_listing_oracle(fc: FetchContext) -> None:
    """LLM-side partialness detection — the regex oracle's language-agnostic superset.

    Runs after `_phase_extract_answer` sets `fc.routing`, so the model's
    `item_total_seen` (a total it READ off the page, in any language) is
    available. Closes the regex noun-list's language-coverage gap for a
    distributed, multi-region tool: a page whose "1123 ürün" / "товаров" / "件"
    count the regex could not match still surfaces an honest partial signal.

    Strict superset — it ONLY adds a signal, never suppresses one:
    - fires only when the regex found NO numeric oracle at all
      (`regex_oracle_total is None`), so a regex "complete" verdict stands;
    - only on a confirmed listing (`record_count` set) whose LLM total exceeds
      the parsed count beyond tolerance;
    - quantifies a prior structural-`listing_more` into a numeric `listing_partial`
      when it can (clearing `items_more` in favour of `items_total`).
    """
    if fc.record_count is None:
        return
    if fc.regex_oracle_total is not None:
        return
    if fc.routing is None:
        return
    total = fc.routing.item_total_seen
    if total is None:
        return
    if content_expectations.assess(loaded=fc.record_count, total=total) != "partial":
        return
    fc.items_loaded = fc.record_count
    fc.items_total = total
    fc.items_more = False
