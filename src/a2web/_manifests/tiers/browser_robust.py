"""browser_robust tier manifest — the robust CDP rung.

A second out-of-band `BrowserTier` instance (named `browser_robust`). Same tier
class as `browser`; the orchestrator hands it the robust (CDP) backend and
dispatches it only as the *second* browser escalation, when the fast `browser`
rung came back thin/blocked (browser-backend-bakeoff).
"""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.settings import AppSettings
from a2web.tiers import Tier
from a2web.tiers.browser import BrowserTier


def _build(_settings: AppSettings) -> Tier | Unavailable:
    return BrowserTier(name="browser_robust")


MANIFEST = PluginManifest(
    name="browser_robust",
    protocol=Tier,
    factory=_build,
    priority=-1,
)
