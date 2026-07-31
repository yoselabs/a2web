"""Shared handler helpers — the byte-identical bits that used to live in
every site handler.

Three helpers:

- `empty_result(url, verdict)` — the empty `TierResult` builder every handler
  duplicates verbatim for short-circuit returns.
- `challenge_verdict(raw_html, content_type)` — the wall check an HTML handler
  runs before reporting `ok`.
- `map_non_ok(outcome, url)` — translates a transport-layer `FetchOutcome`
  into a domain-typed empty `TierResult` for the standard non-ok cases
  (timeout / not_found / rate_limited / other-non-ok). Returns `None` when
  the outcome is `FetchVerdict.ok` so the caller continues. Reddit's
  `status_code == 403` shape-aware branch stays inline — it's the only
  handler-specific HTTP policy and pulling it here would mis-shape the
  abstraction.

(Phase 5 of `fetcher-orchestrator-refactor-v1`.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from http_fetch import FetchVerdict

from ..models import Verdict
from ..packages.block_detector import BlockVerdict, evaluate

if TYPE_CHECKING:
    from http_fetch import FetchOutcome

    from ..tiers import TierResult


def empty_result(url: str, verdict: Verdict) -> TierResult:
    """Return a `TierResult` with empty body + given verdict.

    Imported lazily — `tiers` imports from handlers, so a top-level import
    would close the cycle.
    """
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )


def map_non_ok(outcome: FetchOutcome, *, url: str) -> TierResult | None:
    """Map a non-ok `FetchOutcome` to a `TierResult` via the standard
    FetchVerdict → Verdict table. Returns `None` when `outcome.verdict is
    FetchVerdict.ok` so the caller continues.

    Handlers used to inline the 4-line block; this is the single source of
    truth for the mapping. Handler-specific policy (e.g. Reddit's 403
    shape-aware branch) stays inline at the handler.
    """
    if outcome.verdict is FetchVerdict.ok:
        return None
    if outcome.verdict is FetchVerdict.timeout:
        return empty_result(url, Verdict.timeout)
    if outcome.verdict is FetchVerdict.not_found:
        return empty_result(url, Verdict.not_found)
    if outcome.verdict is FetchVerdict.rate_limited:
        return empty_result(url, Verdict.rate_limited)
    return empty_result(url, Verdict.connection_error)


# Wall verdicts, and ONLY wall verdicts. `evaluate` also returns thinness
# verdicts (`length_floor`, `blank_page`) — those are the gate's business. A
# handler asks only "did this upstream answer with a challenge?"; whether what
# arrived is too thin to be useful is decided later, with more information.
_WALL_VERDICTS = frozenset({BlockVerdict.anti_bot, BlockVerdict.block_page_detected})


def challenge_verdict(raw_html: str, *, content_md: str) -> Verdict | None:
    """Return a wall `Verdict` when `raw_html` carries a challenge fingerprint,
    else `None`.

    **The FIRST `handlers/` → `packages/` import.** `tach.toml` permits it
    ("domain code may freely import from any package"), but no handler had used
    the edge before, so it is named here rather than discovered later as an
    accident. The alternative — re-implementing a fingerprint check inside
    `handlers/` — would put a SECOND wall catalogue in the tree, and the
    catalogue's whole value is that it is one bounded list with one set of
    witnesses.

    **Why the caller must pass the REAL `content_md`, thin or not.** The obvious
    move is to pass `""` and force every length-gated branch on, so that a
    verbose challenge is caught as readily as a terse one. That was tried and it
    is WRONG, proven on the first live run: the wikipedia article for Python
    turned `block_page_detected` because a citation title — "PEP 466 - Network
    Security Enhancements for Python 2.7.x" — matched the catalogue's
    `\\bnetwork security\\b` marker.

    The catalogue holds two kinds of marker and they are not interchangeable.
    Vendor fingerprints (turnstile widget ids, Akamai cookie names, Baxia asset
    paths) cannot occur in prose, and `evaluate` matches those at ANY length.
    The rest are English sentences — "access denied", "network security",
    "checking your browser" — which are safe ONLY because the length gate means
    a page with a full article body never reaches them. Forcing them on removes
    the one thing making them acceptable.

    So the honest guarantee is narrower than "length-independent": a
    fingerprinted wall is caught at any length; a prose-only challenge is caught
    while it is thin, which is what a challenge page normally is. Widening that
    needs a tighter marker, not a wider gate.

    **Why no `content_type`.** `evaluate` short-circuits to
    `content_type_mismatch` for a non-HTML header, which at gate time is right —
    a JSON response is not a page. Here it would be a hole: the header is chosen
    by the same upstream that served the challenge, so a wall labelled
    `application/json` would switch its own detection off. The handler asked for
    a page; this scans the body it actually got, and the header gets no vote.

    **Why `Verdict | None` and not a `TierResult`.** A failover loop must be able
    to distinguish "walled, try the next upstream" from "walled, give up" — it
    is the CALLER that knows whether untried upstreams remain. A helper returning
    a terminal `TierResult` (as `map_non_ok` does) would force the first reading
    and could not serve the loop.
    """
    result = evaluate(content_md=content_md, raw_html=raw_html, content_type=None)
    if result.verdict not in _WALL_VERDICTS:
        return None
    return Verdict(result.verdict.value)


__all__ = ["challenge_verdict", "empty_result", "map_non_ok"]


def truncation_note(shown: int, total: int | None, *, noun: str) -> str:
    """A `N of M` partial-view note, or `""` when nothing was withheld.

    Ported from `arxiv._render_listing`, which was the only handler declaring
    its own truncation. Every other capped renderer silently dropped the tail:
    `v2ex` rendered `_MAX_REPLIES` of a longer list, `discourse` `_MAX_TOPICS`,
    `hn` 30 hits — each holding the full collection and discarding its length.

    That silence is the ADR-0009 failure on the sufficiency axis. The caller
    cannot distinguish "the thread has 200 replies" from "a2web rendered the
    first 200 of 900", so a distilled answer reads as complete over a body that
    was cut. Where the handler knows both numbers, it must say so.

    Only a total that EXCEEDS what was rendered is news; an equal or smaller one
    would turn "25 of 25" into noise, or worse, into a false shortfall.
    """
    if total is None or total <= shown:
        return ""
    return f"_Showing {shown} of {total} {noun} — this is a partial view._\n"
