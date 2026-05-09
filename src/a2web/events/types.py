"""Phase-boundary events emitted by the fetch orchestrator."""

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


Event = TierStarted | TierEnded | StageStarted | StageEnded
