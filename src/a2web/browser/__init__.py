"""Camoufox browser pool — lazy-launched, per-host context isolation.

Exports nothing at top-level on purpose: importing the package must
not pay the Camoufox import cost. Use `from a2web.browser.pool import
BrowserPool` (only inside `state.ensure_browser_pool`, which itself is
only invoked from the browser tier path).
"""
