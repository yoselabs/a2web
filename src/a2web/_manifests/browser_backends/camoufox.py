"""Camoufox backend manifest — GATED off (browser-backend-bakeoff).

Camoufox is the one known fingerprint-strong engine, but its pip build pins a
stale Firefox and the juggler fix that survives Playwright ≥1.60 (PR #625,
commit `b05563291d`) is merged-but-unreleased. Until a Camoufox build ships
that commit, this manifest surfaces `Unavailable` so the registry drops it and
`settings.browser_backend = "camoufox"` degrades through `ResourceUnavailable`
rather than crashing on a version-skewed driver.

The launcher code (`camoufox_launcher` + `PlaywrightBackend`) is retained
intact — re-enabling is a one-line flip of `_build` back to constructing the
backend, plus re-adding the `camoufox` dependency. The gated build body is
kept (commented) so the wiring is obvious when the gate lifts.
"""

from __future__ import annotations

from a2web._plugin import PluginManifest, Unavailable
from a2web.packages.browser_backends import BrowserBackend
from a2web.settings import AppSettings

_GATE_REASON = "camoufox gated: Firefox build lacks juggler #625 (b05563291d); re-enable when a build ships it + re-add the camoufox dep"


def _build(_settings: AppSettings) -> BrowserBackend | Unavailable:
    # GATED. To re-enable once Camoufox ships #625 (and the `camoufox` dep is
    # back in pyproject), restore:
    #   from a2web.packages.browser_backends import PlaywrightBackend, camoufox_launcher
    #   from a2web.state import _emit_browser_stderr
    #   return PlaywrightBackend(camoufox_launcher, name="camoufox",
    #       max_pool=_settings.browser_max_pool, idle_timeout_s=_settings.browser_idle_timeout_s,
    #       page_budget_s=_settings.browser_page_budget_s, stderr_sink=_emit_browser_stderr)
    return Unavailable(_GATE_REASON)


MANIFEST = PluginManifest(name="camoufox", protocol=BrowserBackend, factory=_build, requires=())
