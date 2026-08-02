"""Tier/stage event emission and the two host helpers. A utils leaf."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from .. import log as a2web_log
from ..events import TierEnded, TierStarted
from ..models import Verdict

# --------------------------------------------------------------------- #
# Event emission helpers
# --------------------------------------------------------------------- #


# Note: typed events emit directly via `await a2web_log.info(event)`.
# a2kit resolves a dataclass/pydantic instance to a `LogRecord` whose message
# is the type name and whose payload dict rides on `record.fields`
# (`dataclasses.asdict` + Enum.value coercion). No flattener needed at this seam.


# --------------------------------------------------------------------- #
# Tier emission helpers — shared by tier loop + escalators
# --------------------------------------------------------------------- #


async def _emit_tier_started(
    *,
    step: str,
    host: str | None,
    start_perf: float,
) -> int:
    """Emit `TierStarted` at the current perf-clock tick; return the relative ms."""
    start_ms = int((time.perf_counter() - start_perf) * 1000)
    await a2web_log.info(TierStarted(t_ms=start_ms, step=step, host=host))
    return start_ms


async def _emit_tier_ended(
    *,
    step: str,
    engine: str | None,
    verdict: Verdict,
    start_ms: int,
    start_perf: float,
    extra: dict[str, str | int] | None = None,
) -> int:
    """Emit `TierEnded` and return the elapsed `dur_ms` (relative to `start_ms`)."""
    dur_ms = int((time.perf_counter() - start_perf) * 1000) - start_ms
    await a2web_log.info(
        TierEnded(
            t_ms=start_ms,
            step=step,
            engine=engine,
            verdict=verdict,
            dur_ms=dur_ms,
            extra=extra or {},
        ),
    )
    return dur_ms


def _format_age(age_hours: float | None) -> str:
    if age_hours is None:
        return "never"
    if age_hours < 1:
        return f"{age_hours * 60:.0f}m"
    return f"{age_hours:.0f}h"


def _host(url: str) -> str | None:

    return urlparse(url).hostname
