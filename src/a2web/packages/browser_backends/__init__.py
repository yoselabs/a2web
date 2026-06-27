"""Browser rendering-engine backends — swappable behind `BrowserBackend`.

Domain-free boundary (mirrors `llm_extract`'s `Provider` seam): the Protocol
and its value objects carry no domain types. The domain (the browser tier +
`select_backend`) converts `Cookie` → `BackendCookie` and maps `RenderOutcome`
→ `Verdict`/`OperatorHint`.
"""

from __future__ import annotations

from .base import BackendCookie, BrowserBackend, RenderedPage, RenderOutcome
from .patchright import patchright_launcher
from .playwright import PlaywrightBackend, camoufox_launcher, chromium_launch
from .zendriver import ZendriverBackend

__all__ = [
    "BackendCookie",
    "BrowserBackend",
    "PlaywrightBackend",
    "RenderOutcome",
    "RenderedPage",
    "ZendriverBackend",
    "camoufox_launcher",
    "chromium_launch",
    "patchright_launcher",
]
