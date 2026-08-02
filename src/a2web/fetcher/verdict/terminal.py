"""ADR-0009's systematic terminal floor — a fetch never silently misses."""

from __future__ import annotations

from ...actions.terminal import TerminalOutcome, classify_terminal
from ...hints import (
    content_not_found_hint,
    content_thin_hint,
    try_user_browser_hint,
)
from ...models import Verdict
from ..context import FetchContext
from ..verdict.promotions import _has_browser_hint, _has_hint


def _apply_terminal(fc: FetchContext) -> None:
    """The single systematic terminal floor (ADR-0009), driven by `classify_terminal`.

    Once per fetch, at the end of the pipeline: classify the decision log into a
    `TerminalOutcome` and attach the matching hint. This is the one chokepoint —
    it runs regardless of which phase terminated the cascade, and dedups against a
    handler's eager emission. The classifier reads the OBSERVATIONS (not the
    resolved-verdict projection), so a corroborated dead URL is seen as gone, not
    dressed as a wall.

    - `wall` → the critical `try_user_browser` prescription (content/transport/thin).
    - `gone_confirmed` → an authoritative handler "gone" stays SILENT (definitive);
      an HTTP-404 corroborated by >=2 tiers gets the INFO `content_not_found`
      (a dead URL is not a wall — no browser command).
    - `gone_unverified` → the WARNING `content_not_found` with the soft-404 caveat
      + browser escape hatch.
    - `thin_unverified` / `empty_unverified` → the WARNING `content_thin` (a
      retrieved thin 200 with no wall evidence — an ambiguous thin page, or one an
      empty-result marker leaned empty on but the promotion conjunction did not
      hold); the retrieved body is attached to the envelope by the response
      builder. NEVER `try_user_browser`.
    - `operator_error` / `unreachable` → no hint HERE. `paid_auth_error` carries
      its own critical `paid_auth_error_hint`, emitted at the paid tier where the
      rejecting tier's name is known (this seam only sees the resolved verdict);
      dns/content_type_mismatch are honestly terminal.
    """
    if fc.resolved_verdict() is Verdict.ok:
        return
    # A corroborated empty was promoted to `ok` upstream (`_phase_empty_promotion`)
    # — it owns its own INFO `content_empty` hint; the failure floor stands down.
    if fc.empty_confirmed:
        return
    # A corroborated complete-small-page that produced an answer is a success, not a
    # thin failure — stand down so no `content_thin` klaxon is attached. If it did NOT
    # produce an answer (`small_page_promoted()` False), the floor proceeds and the
    # honest `content_thin` failure is attached below (no silent miss).
    if fc.small_page_promoted():
        return
    outcome = classify_terminal(fc.observations, fc.resolved_verdict())
    fc.terminal = outcome  # carried to the response builder; never re-derived from hints
    if outcome is TerminalOutcome.wall:
        if not _has_browser_hint(fc):
            fc.operator_hints.append(try_user_browser_hint(fc.final_url))
    elif outcome is TerminalOutcome.gone_confirmed:
        # An authoritative handler "gone" is definitive and stays silent; a
        # corroborated HTTP 404 surfaces an honest info-level not-found.
        authoritative_gone = any(o.authoritative and o.verdict is Verdict.not_found for o in fc.observations)
        if not authoritative_gone and not _has_hint(fc, "content_not_found"):
            fc.operator_hints.append(content_not_found_hint(fc.final_url, verified=True))
    elif outcome is TerminalOutcome.gone_unverified:
        if not _has_hint(fc, "content_not_found"):
            fc.operator_hints.append(content_not_found_hint(fc.final_url, verified=False))
    elif outcome in (TerminalOutcome.thin_unverified, TerminalOutcome.empty_unverified):
        if not _has_hint(fc, "content_thin"):
            fc.operator_hints.append(content_thin_hint(fc.final_url))
