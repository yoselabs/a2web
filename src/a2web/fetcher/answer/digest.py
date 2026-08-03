"""The `{{n}}` link digest: build, and rehydrate against the closed set (ADR-0014)."""

from __future__ import annotations

from dataclasses import replace

from ...link_digest import LinkDigest, build_digest
from ...log import log_warning
from ...packages.llm_extract import OtherPageBoundary, RouterPayload
from ..context import FetchContext

# `_apply_terminal` is NOT called here — the coordinator owns it, so the
# never-silently-miss floor runs on the deadline path too. Calling it in
# both places would run it twice on every successful fetch.


# Server-side ceiling on digest size — a circuit breaker on token cost, never a
# target surfaced to the model (relevance is the model's job, ADR-0012).
_DIGEST_LINK_CAP = 200
# Candidate sources that stand in for `structural_form ∈ {product, listing}`
# BEFORE the LLM classifies (structural_form is post-hoc): a product page yields
# a json_synth (Product schema) candidate; a listing yields record_synth.
_DIGEST_GATE_SOURCES = frozenset({"json_synth", "record_synth"})


def _build_link_digest(fc: FetchContext) -> LinkDigest | None:
    """Build the link digest when the page looks product/listing-shaped.

    Pre-LLM gate: feed the digest only when a structured (json_synth /
    record_synth) candidate is present — the signal a product/listing page
    leaves before the model runs. Prose-only articles skip it and pay nothing.
    """
    if not fc.links:
        return None
    if not any(c.source in _DIGEST_GATE_SOURCES for c in fc.content_candidates):
        return None
    digest = build_digest(fc.links, page_url=fc.final_url or "", limit=_DIGEST_LINK_CAP)
    return digest or None


def _rehydrate_routing_handles(routing: RouterPayload | None, digest: LinkDigest | None) -> RouterPayload | None:
    """Resolve `other_pages` `{{n}}` handles to real hrefs against the closed set.

    Each boundary entry carrying a handle is looked up in the digest: a hit
    becomes a rehydrated entry (real `url`, `off_domain` from the affordance, no
    handle); a miss is dropped — a handle the digest doesn't know is never
    guessed into a URL. Legacy entries that already carry a `url` pass through.
    """
    if routing is None or not routing.other_pages:
        return routing
    by_handle = {e.handle: e for e in digest.entries} if digest else {}
    resolved: list[OtherPageBoundary] = []
    for entry in routing.other_pages:
        if entry.handle is not None:
            aff = by_handle.get(entry.handle)
            if aff is None:
                # Closed-set violation — the model referenced a handle the
                # digest doesn't know. Drop it (never guess a URL) but surface
                # the recovery via the unified `llm_wobble` key, consistent with
                # the other LLM-contract boundaries. The fetch still succeeds.
                log_warning(
                    "llm_wobble",
                    boundary="other_pages_handle",
                    field="handle",
                    tolerance="skip",
                    handle=entry.handle,
                )
                continue
            resolved.append(replace(entry, url=aff.href, off_domain=aff.off_domain, handle=None))
        elif entry.url:
            resolved.append(entry)
    return replace(routing, other_pages=tuple(resolved))
