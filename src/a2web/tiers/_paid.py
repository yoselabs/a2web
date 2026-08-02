"""Shared internals for the paid last-resort tiers (Zyte, Firecrawl).

Both paid tiers map HTTP status to the same closed `Verdict` set: auth/billing
failures (401/402/403) become the authoritative `paid_auth_error` that the
orchestrator fail-loud-STOPs on; everything else follows the usual tier mapping.
Kept in one place so the two tiers cannot drift.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from ..models import Verdict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ..state import AppState


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


@asynccontextmanager
async def paid_api_breaker(state: AppState, api_host: str) -> AsyncIterator[None]:
    """Wrap a paid-API call in a per-API circuit breaker.

    **Keyed on the API host, never the target.** A paid tier does not dial the
    target — it asks a vendor to. Keying on the target would share the raw
    tier's breaker, so a host that just failed on raw would short-circuit the
    LAST-RESORT tier before it was tried, which is precisely backwards: the paid
    tier exists for hosts the free ladder could not reach. (Same reasoning as
    `tiers/jina.py`'s `r.jina.ai` breaker.)

    Only the CALL goes inside. The exception must reach the breaker for it to
    record anything — `http_fetch`'s breaker shipped inert for months because
    the work it wrapped never raised — so the caller's `except` clauses sit
    OUTSIDE this context manager, and an open breaker surfaces as the same
    `Verdict.connection_error` a dial failure would.
    """
    breaker = await state.breakers.get_breaker(api_host) if state.breakers is not None else None
    if breaker is None:
        yield
        return
    async with breaker:
        yield
