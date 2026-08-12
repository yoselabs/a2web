"""Is a page section withheld behind an in-page interaction we cannot perform?

The presence-axis sibling of `completeness.py`'s sufficiency check (ADR-0020,
grounded absence). Mirrors `_phase_listing_completeness`'s shape: pure verdict
over already-retrieved raw HTML, no fetching, no LLM call — the extractor's
relevance judgment (which detected gate, if any, blocks THIS question) happens
later, at the answer seam (`fetcher/answer/digest.py`), against the closed set
this phase produces.
"""

from __future__ import annotations

from ...gated_sections import detect_gated_sections
from ..context import FetchContext


def _phase_gated_sections(fc: FetchContext, *, raw_html: str) -> None:
    """Detect click-gated disclosure controls in `raw_html`.

    Recomputes `fc.gated_sections` from scratch on every call rather than
    accumulating — the simplest form of the symmetric clear this needs: a
    later escalation that installs different `raw_html` (e.g. a render that
    happened to expand a section) naturally drops any gate whose panel is now
    populated, without a separate retraction step.

    Silent when detection finds nothing — `fc.gated_sections` stays the empty
    tuple its field default already is, so a page with no gated sections costs
    one detector pass and nothing else.
    """
    fc.gated_sections = detect_gated_sections(raw_html).entries
