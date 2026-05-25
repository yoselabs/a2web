"""Typed escalation signal — package-owned boundary type.

`EscalationSignal` is the typed replacement for the string `suggested_tier`
field that previously lived on `Observation` and `BlockResult`. The Literal
`NextTier` constrains the value space; the `reason` carries a human-readable
diagnostic that aligns with the producing source's subsystem annotation.

The signal is evidence-only. The planner (`actions.playbook.decide_next`)
remains the sole authority on whether to act — per-fetch caps still gate
execution. (Phase 4 of `fetcher-orchestrator-refactor-v1`.)

Lives in `packages/` (no domain imports) because `block_detector.py` — a
package — produces it. Domain code (`decision_log.py`, `actions/playbook.py`,
`fetcher.py`) imports it from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NextTier = Literal["browser", "tls_impersonate", "archive"]


@dataclass(slots=True, frozen=True)
class EscalationSignal:
    """One typed escalation recommendation. Frozen — observations are
    immutable, and signals attached to them inherit that contract."""

    next_tier: NextTier
    reason: str


__all__ = ["EscalationSignal", "NextTier"]
