"""Shared handler helpers — the byte-identical bits that used to live in
every site handler.

Two helpers:

- `empty_result(url, verdict)` — the empty `TierResult` builder every handler
  duplicates verbatim for short-circuit returns.
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

from ..models import Verdict
from ..packages.http_fetch import FetchVerdict

if TYPE_CHECKING:
    from ..packages.http_fetch import FetchOutcome
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


__all__ = ["empty_result", "map_non_ok"]
