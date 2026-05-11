"""Phase-boundary events emitted by the fetch orchestrator.

These types are registered on `app.ldd.events` in `server.py` so a2kit can
route them through the typed-emit path. Sinks (OTel + the wire bridge that
a2kit owns) receive them as `LddEmission` payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Verdict


@dataclass(slots=True)
class TierStarted:
    t_ms: int
    step: str
    engine: str | None = None
    host: str | None = None
    proxy: str | None = None


@dataclass(slots=True)
class TierEnded:
    t_ms: int
    step: str
    engine: str | None
    verdict: Verdict
    dur_ms: int
    extra: dict[str, str | int] = field(default_factory=dict)


@dataclass(slots=True)
class StageStarted:
    t_ms: int
    step: str  # "extract" | "gate" | "fit" | "cache_write"


@dataclass(slots=True)
class StageEnded:
    t_ms: int
    step: str
    verdict: Verdict
    dur_ms: int
    extra: dict[str, str | int] = field(default_factory=dict)


@dataclass(slots=True)
class TierHeartbeat:
    """Mid-tier liveness pulse from inside slow tiers (browser, archive).

    Browser tier emits every 2s during page-load wait. Archive tier emits per
    hedged-request boundary. Closes the "silent until timeout" diagnostic
    blind spot — both OTel and humans see "still alive at 22s, 24s..." when
    a tier is taking its time.
    """

    t_ms: int
    step: str  # "browser" | "archive"
    elapsed_in_tier_ms: int
    detail: dict[str, str] = field(default_factory=dict)


Event = TierStarted | TierEnded | StageStarted | StageEnded | TierHeartbeat
