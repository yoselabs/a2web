"""ZyteTier manifest — env-gated paid last resort, dispatched out-of-band."""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.zyte import ZyteTier


def _build(settings: AppSettings) -> Tier | Unavailable:
    if not settings.zyte_key:
        return Unavailable("no zyte_key")
    return ZyteTier()


# priority=-1: out-of-band. Registered in REGISTRY but never in TIER_ORDER —
# the orchestrator dispatches it only on the paid-escalation planner action,
# after the free/proxied ladder is exhausted.
MANIFEST = PluginManifest(
    name="zyte",
    protocol=Tier,
    factory=_build,
    requires=("zyte_key",),
    priority=-1,
)
