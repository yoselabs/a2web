"""FirecrawlTier manifest — env-gated paid last resort, dispatched out-of-band."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.firecrawl import FirecrawlTier


def _build(settings: AppSettings) -> Tier | Unavailable:
    if not settings.firecrawl_key:
        return Unavailable("no firecrawl_key")
    return FirecrawlTier()


# priority=-1: out-of-band. Registered in REGISTRY but never in TIER_ORDER —
# the orchestrator dispatches it only on the paid-escalation planner action,
# after the free/proxied ladder is exhausted.
MANIFEST = PluginManifest(
    name="firecrawl",
    protocol=Tier,
    factory=_build,
    requires=("firecrawl_key",),
    priority=-1,
)
