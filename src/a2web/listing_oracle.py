"""Generic item-count oracle for listing pages (listing-completeness Slice 1).

A *listing oracle* is the authoritative count of items a listing page claims to
hold — the number a browser user sees ("40 sonuç", "1,234 results") or the site
declares in structured data (`ItemList.numberOfItems`). Compared against the
parsed record count, it resolves whether a fetched listing is complete or a
truncated infinite-scroll sample (the sufficiency axis of ADR-0009).

Pure, settings-free, never raises: any failure yields `None` ("no oracle"), and
the caller treats a page with no oracle as making no completeness claim. Uses
regex over the raw HTML (no JSON parse) so a malformed `ld+json` block or an
unusual count phrasing degrades to `None` rather than an error.
"""

from __future__ import annotations

import re

# Structured: JSON-LD / microdata `numberOfItems` (quoted or bare). Highest
# reliability — an explicit, unambiguous machine count.
_NUMBER_OF_ITEMS_RE = re.compile(r'"?numberOfItems"?\s*[:=]\s*"?(\d[\d.,]*)"?', re.IGNORECASE)

# Visible count: a number immediately bound to an item/result noun. Anchored to
# the noun so popularity numbers ("1000 reviews", "4.7 rating", "12 comments")
# are NOT misread as an item total. Turkish (sonuç / ürün / adet) + English.
_VISIBLE_COUNT_RE = re.compile(
    r"(\d[\d.,]*)\s*(?:results?|sonuç|sonuc|ürün|urun|adet|products?|items?|listings?)\b",
    re.IGNORECASE,
)

# Structural "more exists" affordances — pagination / infinite-scroll controls
# that imply items beyond the rendered batch. Consulted ONLY as a fallback when
# no numeric oracle is extractable, and ONLY on a page already confirmed to be a
# listing (a parsed record set). Anchored to strong, listing-specific markers so
# a bare "next article" nav link on a non-listing never fires: `rel="next"` (the
# HTML pagination standard) and explicit load-more / next-page controls
# (English + Turkish `daha fazla` / `sonraki sayfa`). The per-item-generic "show
# more" expander is deliberately excluded to keep false positives low.
_REL_NEXT_RE = re.compile(r"""rel\s*=\s*["']?[^"'>]*\bnext\b""", re.IGNORECASE)
_MORE_CONTROL_RE = re.compile(
    r"(?:load[-_\s]?more|infinite[-_\s]?scroll|daha\s+fazla|sonraki\s+sayfa|next\s+page)",
    re.IGNORECASE,
)


def _parse_count(raw: str) -> int | None:
    """Parse a matched count, stripping thousands separators (',' and '.')."""
    digits = raw.replace(",", "").replace(".", "").strip()
    return int(digits) if digits.isdigit() else None


def listing_oracle(html: str) -> int | None:
    """Extract the advertised item total from a listing page, or `None`.

    Reliability order: structured `numberOfItems` first, then the largest
    noun-anchored visible count (the largest plausible match beats a stray small
    number like the current page size). `None` when neither is present.
    """
    if not html:
        return None
    structured = _NUMBER_OF_ITEMS_RE.search(html)
    if structured is not None:
        value = _parse_count(structured.group(1))
        if value is not None:
            return value
    visible = [v for m in _VISIBLE_COUNT_RE.finditer(html) if (v := _parse_count(m.group(1))) is not None]
    return max(visible) if visible else None


def listing_has_more(html: str) -> bool:
    """True when the page exposes a pagination / infinite-scroll affordance.

    The structural fallback to `listing_oracle`: when a listing carries records
    but advertises no numeric total, a `rel="next"` link or an explicit
    load-more / next-page control is evidence that items exist beyond the
    rendered batch. Callers use this only after confirming the page is a listing
    with no numeric oracle — the record-set gate is what keeps a stray "next"
    link on an ordinary article from being read as a truncated listing.
    """
    if not html:
        return False
    return bool(_REL_NEXT_RE.search(html) or _MORE_CONTROL_RE.search(html))


__all__ = ["listing_has_more", "listing_oracle"]
