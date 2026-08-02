"""`escalate` — the one seam through which content may be installed after the gate.

Dispatch a rung, then comprehend whatever it installed. Escalators do not call
comprehension forward; that is what made it possible for three paths to run
three different amounts of it.
"""

from __future__ import annotations

from enum import Enum

from ....state import AppState
from ...comprehension.gate import _regate_after_escalation
from ...comprehension.ladder import _run_extraction_escalation
from ...context import FetchContext
from ...sufficiency.completeness import _phase_listing_completeness

# Imported as MODULES, not names. `from .browser import _escalate_browser`
# freezes the reference at import time, so a test that fakes the rung would
# silently keep calling the real one — the same trap the dispatch table hit
# in §3.2, reintroduced by the file split. Attribute lookup happens at call
# time and stays fake-able.
from . import archive as _archive_mod
from . import browser as _browser_mod
from . import paid as _paid_mod


class Rung(Enum):
    """What an escalation dispatches. The vocabulary `escalate` switches on."""

    browser = "browser"
    paid = "paid"
    archive = "archive"


async def _comprehend(fc: FetchContext) -> None:
    """Read whatever was just installed: the extraction ladder, sufficiency, the gate.

    THE single downstream of an escalation. It reads `fc` rather than taking the
    tier result, so it cannot be handed a subset of what was installed — which is
    how the three escalation paths came to run three different amounts of it:
    browser and paid ran the ladder but never the sufficiency check (H1), and the
    post-gate archive path ran NEITHER while re-gating anyway, reporting a
    verdict over content nothing had read.

    The html guard is the paid tier's, deliberately, not the browser's. Browser
    decoded any non-empty body, which is equivalent only because a browser body
    is always HTML; paid requires `"html" in content_type` because a
    markdown-native paid tier (Firecrawl) returns clean markdown the ladder must
    not touch. Generalising to the browser's predicate would have run the ladder
    over Firecrawl's markdown — a census merge of these two tails would have
    picked one of them silently.
    """
    raw_html = fc.body.decode("utf-8", errors="replace") if (fc.body and "html" in fc.content_type) else ""
    if raw_html:
        await _run_extraction_escalation(fc, raw_html=raw_html)
        _phase_listing_completeness(fc, raw_html=raw_html)
    _regate_after_escalation(fc)


async def escalate(fc: FetchContext, rung: Rung, *, state: AppState, scroll: bool = False) -> bool:
    """The one seam through which content may be installed after the gate.

    Dispatch, then — if anything landed — comprehend it. Escalators do not call
    comprehension forward any more, and that is the load-bearing change in this
    decomposition: a caller that can call comprehension can call PART of it, and
    four call sites calling four different subsets is precisely the state this
    replaces.

    Returns whether content was installed, which is all any caller needs to know.
    `_phase_obstacle_render` and `_phase_listing_render` compare `content_md`
    before and after instead; that is a weaker test of the same thing (an
    identical re-render reads as "nothing installed") and is left alone here
    because tightening it is a behaviour change, not a move.
    """
    # Dispatched by NAME rather than through a table of function objects. A dict
    # built at import time captures the originals, so a test that patches
    # `_escalate_paid` in this module would silently keep calling the real one —
    # the seam would work and be untestable, which is the failure mode this whole
    # change exists to remove.
    if rung is Rung.browser:
        installed = await _browser_mod._escalate_browser(fc, state=state, scroll=scroll)
    elif rung is Rung.paid:
        installed = await _paid_mod._escalate_paid(fc, state=state, scroll=scroll)
    else:
        installed = await _archive_mod._escalate_archive_post_gate(fc, state=state, scroll=scroll)
    if installed:
        await _comprehend(fc)
    return installed
