"""Content-type-keyed guidance — what matters when reading a page of a given kind.

Part of content-aware refinement guidance. The guidance is keyed off the closed
`structural_form` classification the router-shape extractor already produces — it
is per-**kind**, never per-**site**. A distributed, multi-region tool cannot carry
per-site tables without rotting; a handful of universal content archetypes
(listing / discussion / article / product) is stable across every site and
language. The `tests/architecture/test_content_guidance_no_site.py` invariant
asserts no host / domain / site string ever enters this table.

Consumed at the ask-response seam (`fetcher_response.build_ask_response`), which
surfaces the matching line as an informational `content_guidance` operator hint
for the caller's own model. `None` for a kind with no distinctive guidance —
absence carries the meaning, no hint is emitted.
"""

from __future__ import annotations

# Keyed on `structural_form` values (a2web.models.StructuralForm). Only kinds
# whose "what matters" is non-obvious and actionable carry an entry; the rest
# resolve to None and emit no guidance. NEVER add a host, domain, or site name
# here — guidance keys on the content archetype, not the source.
KIND_GUIDANCE: dict[str, str] = {
    "listing": (
        "Listing page: the rows shown may be a truncated and/or sorted subset, not the whole set. "
        "Check completeness and beware selection bias (a price/date sort makes the sample "
        "unrepresentative for a 'best' judgment); narrow by an axis and re-query rather than "
        "judging the visible rows as the full field."
    ),
    "thread": (
        "Discussion page: weigh consensus against dissent and recency; the top or first reply is "
        "not automatically the truth. Read positions across the thread before concluding."
    ),
    "product": ("Product page: the load-bearing facts are price, key specs, availability, and the gist of reviews — not marketing copy."),
}


def kind_guidance(structural_form: str | None) -> str | None:
    """Return the one-line guidance for a classified page kind, or None.

    Pure and total: an unknown / unclassified kind yields None (no guidance).
    """
    if structural_form is None:
        return None
    return KIND_GUIDANCE.get(structural_form)


__all__ = ["KIND_GUIDANCE", "kind_guidance"]
