"""Empty-confirmation predicate — the upstream sibling of `classify_terminal`.

`classify_terminal` is a FAILURE taxonomy; an `ok` empty result must be decided
BEFORE it. `is_confirmed_empty` is the promotion conjunction: a retrieved thin
page is a COMPLETE "no results" answer only under hard, multi-signal corroboration
that rules out the walled-API fake-empty (an SPA shell that 200s and renders an
authentic "0 results" while its data API was blocked). Pure, total, no I/O — the
same substrate as the classifier.

The false-positive asymmetry is the whole reason this is a conjunction, not a
catalogue lookup: a false-positive wall over-warns (cheap); a false-positive empty
promotes a real wall to `ok: "no results"` — a confident silent miss that
terminates the caller's search plan (the exact ADR-0009 harm). So text alone (the
empty marker) never promotes; every term below must hold.

Corroboration is by an independent BROWSER render, not a foreign-egress reader: a
thin HTTP 200 WINS the tier loop (raw returned `ok`), so the free jina rung never
runs on it — the second independent retrieval a thin page actually gets is the
planner's browser escalation. That is the stronger corroborator here anyway: a
real anti-detect browser rendered the page AND watched every subresource (the
`has_subresource_block_evidence` guard), so a walled-API fake-empty cannot slip
through. The residual (an IP-reputation wall that fake-empties our HTTP AND browser
egress identically) is narrow and the attached `thin_content` is its mitigation.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..decision_log import Observation, ObservationKind
from ..domain import is_search_shaped
from ..models import Verdict
from .terminal import has_hard_wall_evidence, has_subresource_block_evidence

# Statuses that betray a wall anywhere in the log — an empty reading is not
# credible if any tier was refused or challenged.
_CHALLENGE_STATUSES = frozenset({401, 403, 429})

# The source tag the fetcher stamps on the gate re-evaluation after an escalation
# install (`fetcher._regate_after_escalation`). A regate carrying the empty marker
# means a real browser rendered the page and it was STILL an empty result.
_REGATE_SOURCE = "regate"
_EMPTY_MARKER = "empty_result"


def is_confirmed_empty(observations: Sequence[Observation], url: str) -> bool:
    """True when a thin retrieved page is a corroborated empty result — safe to
    promote to `ok` "no results". Pure and total; every conjunction term must hold:

    1. NO hard-wall gate evidence and NO subresource-block evidence anywhere;
    2. NO challenge status (401/403/429) on any observation;
    3. an independent BROWSER render read the page as empty too — a regate gate
       outcome carrying the empty-result marker (the browser is a distinct retrieval
       mechanism AND it watched every subresource, so a fake-empty cannot pass);
    4. an HTTP tier independently returned a body (the raw retrieval);
    5. the URL is search-shaped (an empty reading of a non-search route is suspect).
    """
    if has_hard_wall_evidence(observations) or has_subresource_block_evidence(observations):
        return False
    if any(o.status_code in _CHALLENGE_STATUSES for o in observations):
        return False
    browser_read_empty = any(
        o.kind is ObservationKind.gate_outcome and o.source == _REGATE_SOURCE and o.subsystem == _EMPTY_MARKER
        for o in observations
    )
    if not browser_read_empty:
        return False
    if not any(o.kind is ObservationKind.tier_outcome and o.verdict is Verdict.ok for o in observations):
        return False
    return is_search_shaped(url)


__all__ = ["is_confirmed_empty"]
