"""Shared internals for the paid last-resort tiers (Zyte, Firecrawl).

Both paid tiers map HTTP status to the same closed `Verdict` set: auth/billing
failures (401/402/403) become the authoritative `paid_auth_error` that the
orchestrator fail-loud-STOPs on; everything else follows the usual tier mapping.
Kept in one place so the two tiers cannot drift.
"""

from __future__ import annotations

from ..models import Verdict


def paid_verdict_for_status(status: int) -> Verdict:
    """Map a paid-service HTTP status to a closed `Verdict`.

    401/402/403 → `paid_auth_error` (bad key / exhausted billing — a loud
    operator error the orchestrator must surface, never mask).
    """
    if status in (401, 402, 403):
        return Verdict.paid_auth_error
    if status == 429:
        return Verdict.rate_limited
    if status == 404:
        return Verdict.not_found
    if status >= 400:
        return Verdict.connection_error
    return Verdict.ok
