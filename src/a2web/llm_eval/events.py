"""Bench-only event types for live progress visibility.

Emitted from `EvalSuite._run_one` and consumed by `LiveSink` (stdout). These
are intentionally separate from `a2web.events.types` (orchestrator-level
phase events) because their granularity is the bench cell, not the fetch
phase — and we route them differently (always-stdout, not OTel).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CellVerdict = Literal["ok", "fail"]
FailureReason = Literal[
    "system_raised",
    "empty_answer",
    "judge_failed",
    "block_page",
    "timeout",
    "contract_violation",
]


@dataclass(slots=True, frozen=True)
class CellStarted:
    slug: str
    system_name: str
    url: str
    started_at: str  # ISO-8601 UTC


@dataclass(slots=True, frozen=True)
class CellEnded:
    slug: str
    system_name: str
    url: str
    total_ms: int
    verdict: CellVerdict
    failure_reason: FailureReason | None
    cost_usd: float
    cache_hit: bool
    tier: str | None


__all__ = ("CellEnded", "CellStarted", "CellVerdict", "FailureReason")
