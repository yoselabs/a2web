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

from ..models import Heading, NextLink, OperatorHint, Verdict
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
    # v0.7 link-discovery: candidates populated by site handlers on listing-
    # style URLs. Empty list when the URL is terminal (single thread, single
    # paper, etc.) or no handler knows the page schema.
    next_links: list[NextLink] = field(default_factory=list)


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
        **kwargs: Any,
    ) -> TierResult: ...


from .archive import ArchiveTier  # noqa: E402 — re-export for tests
from .browser import BrowserTier  # noqa: E402
from .jina import JinaTier  # noqa: E402
from .raw import RawTier  # noqa: E402 — circular import avoidance
from .site_handler import SiteHandlerTier  # noqa: E402


def _load_tier_registry() -> tuple[dict[str, Tier], tuple[str, ...]]:
    """Walk `_manifests/tiers/` once at import. Returns (REGISTRY, TIER_ORDER).

    REGISTRY includes every tier (priority-aware tiers + out-of-band tiers
    with priority=-1). TIER_ORDER includes only priority >= 0, sorted desc —
    that's the main tier-loop sequence. Archive + browser (priority=-1) are
    dispatched out-of-band by the orchestrator's playbook on escalation
    signals; they live in REGISTRY but never in TIER_ORDER.
    """
    from .._plugin import load_surface_sorted
    from ..settings import AppSettings

    pairs = load_surface_sorted("a2web._manifests.tiers", Tier, AppSettings())
    registry = dict(pairs)
    # Re-walk manifest modules for priority. (load_surface_sorted sorts but
    # drops priority; we need it to filter out-of-band tiers from TIER_ORDER.)
    import importlib
    import pkgutil

    pkg = importlib.import_module("a2web._manifests.tiers")
    in_order: list[tuple[int, str]] = []
    for info in pkgutil.iter_modules(pkg.__path__, prefix="a2web._manifests.tiers."):
        module = importlib.import_module(info.name)
        manifest = getattr(module, "MANIFEST", None)
        if manifest is None or manifest.priority < 0:
            continue
        if manifest.name not in registry:
            continue
        in_order.append((manifest.priority, manifest.name))
    in_order.sort(key=lambda kv: -kv[0])
    tier_order = tuple(name for _prio, name in in_order)
    return registry, tier_order


REGISTRY: dict[str, Tier]
TIER_ORDER: tuple[str, ...]
REGISTRY, TIER_ORDER = _load_tier_registry()


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
