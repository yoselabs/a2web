"""Tier protocol + registry — the single point where tier order is encoded.

Adding a new tier means: define it as a class implementing `Tier`,
register it in `REGISTRY`, and insert its name in `TIER_ORDER` at the
right position. The orchestrator reads `TIER_ORDER` and never needs to
know about specific tier implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..models import Verdict
from ..state import AppState


@dataclass(slots=True)
class TierResult:
    body: bytes
    content_type: str
    status_code: int
    final_url: str
    headers: dict[str, str] = field(default_factory=dict)
    tier_extras: dict[str, Any] = field(default_factory=dict)
    verdict: Verdict = Verdict.ok


@runtime_checkable
class Tier(Protocol):
    """One step in the cascade. Tiers MUST NOT raise for routine HTTP failures.

    They translate connection errors / timeouts / bad statuses into a closed
    `Verdict` value and return. Exceptions cross the boundary only on truly
    unexpected programmer errors.
    """

    name: str

    async def fetch(self, url: str, *, state: AppState) -> TierResult: ...


from .archive import ArchiveTier  # noqa: E402
from .jina import JinaTier  # noqa: E402
from .raw import RawTier  # noqa: E402 — circular import avoidance
from .site_handler import SiteHandlerTier  # noqa: E402

# Archive tier is registered but NOT in TIER_ORDER — orchestrator dispatches
# it out-of-band when the playbook returns RetryViaArchive.
TIER_ORDER: tuple[str, ...] = ("site_handler", "raw", "jina")
REGISTRY: dict[str, Tier] = {
    "site_handler": SiteHandlerTier(),
    "raw": RawTier(),
    "jina": JinaTier(),
    "archive": ArchiveTier(),
}


__all__ = ["REGISTRY", "TIER_ORDER", "ArchiveTier", "JinaTier", "RawTier", "SiteHandlerTier", "Tier", "TierResult"]
