"""Tier protocol + registry — the single point where tier order is encoded.

Adding a new tier means: define it as a class implementing `Tier`,
register it in `REGISTRY`, and insert its name in `TIER_ORDER` at the
right position. The orchestrator reads `TIER_ORDER` and never needs to
know about specific tier implementations.

**Escalation-dispatch contract.** Tiers registered in `REGISTRY` but NOT
in `TIER_ORDER` (`archive`, `browser`) are dispatched out-of-band by
the orchestrator's playbook — `archive` on `RetryViaArchive` action,
`browser` on `gate.suggested_tier == "browser"`. They never run in the
default tier loop; they only run as recoveries on signals from the gate
or after-tier actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..models import Heading, OperatorHint, Verdict
from ..state import AppState


@dataclass(slots=True)
class Rendered:
    """Pre-rendered markdown payload from a tier that did its own extraction.

    Site handlers, archive recoveries, and browser results all populate this
    instead of leaving raw HTML for the orchestrator's trafilatura pass.
    """

    content_md: str
    title: str | None = None
    byline: str | None = None
    headings: list[Heading] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Rendered:
        """Build from a loosely-typed render dict produced by handler helpers."""
        return cls(
            content_md=str(d.get("content_md") or ""),
            title=d.get("title"),  # type: ignore[arg-type]
            byline=d.get("byline"),  # type: ignore[arg-type]
            headings=d.get("headings") or [],  # type: ignore[arg-type]
        )


@dataclass(slots=True)
class TierResult:
    body: bytes
    content_type: str
    status_code: int
    final_url: str
    headers: dict[str, str] = field(default_factory=dict)
    verdict: Verdict = Verdict.ok
    # Typed extras (replaces the v0.1 `tier_extras: dict[str, Any]` bag).
    # All fields are optional; populated by the tier that owns the concept.
    pre_rendered: Rendered | None = None
    from_archive: bool = False
    snapshot_age_days: int | None = None
    from_browser: bool = False
    js_executed: bool = False
    browser_wall_ms: int | None = None
    browser_bytes: int | None = None
    operator_hint: OperatorHint | None = None
    no_match: bool = False
    skipped: bool = False
    handler_name: str | None = None
    conditional_hit: bool = False
    archive_source: str | None = None  # "wayback" | "archive.ph"


class Tier(Protocol):
    """One step in the cascade. Tiers MUST NOT raise for routine HTTP failures.

    They translate connection errors / timeouts / bad statuses into a closed
    `Verdict` value and return. Exceptions cross the boundary only on truly
    unexpected programmer errors.

    Unified signature: every tier accepts `proxy_url` and `conditional_extras`
    kwargs. Tiers that don't use them just ignore them. This lets the
    orchestrator dispatch uniformly without an isinstance ladder.
    """

    name: str

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
    ) -> TierResult: ...


from .archive import ArchiveTier  # noqa: E402
from .browser import BrowserTier  # noqa: E402
from .jina import JinaTier  # noqa: E402
from .raw import RawTier  # noqa: E402 — circular import avoidance
from .site_handler import SiteHandlerTier  # noqa: E402

# Archive and browser tiers are registered but NOT in TIER_ORDER — the
# orchestrator's playbook dispatches them out-of-band on escalation signals.
TIER_ORDER: tuple[str, ...] = ("site_handler", "raw", "jina")
REGISTRY: dict[str, Tier] = {
    "site_handler": SiteHandlerTier(),
    "raw": RawTier(),
    "jina": JinaTier(),
    "archive": ArchiveTier(),
    "browser": BrowserTier(),
}


__all__ = [
    "REGISTRY",
    "TIER_ORDER",
    "ArchiveTier",
    "BrowserTier",
    "JinaTier",
    "RawTier",
    "Rendered",
    "SiteHandlerTier",
    "Tier",
    "TierResult",
]
