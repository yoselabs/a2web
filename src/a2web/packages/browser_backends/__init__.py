"""Browser rendering-engine backends — swappable behind `BrowserBackend`.

Domain-free boundary (mirrors `llm_extract`'s `Provider` seam): the Protocol
and its value objects carry no domain types. The domain (the browser tier +
`select_backend`) converts `Cookie` → `BackendCookie` and maps `RenderOutcome`
→ `Verdict`/`OperatorHint`.
"""

from __future__ import annotations

from .base import BackendCookie, BrowserBackend, RenderedPage, RenderOutcome
from .playwright import PlaywrightBackend, camoufox_launcher

__all__ = [
    "BackendCookie",
    "BrowserBackend",
    "PlaywrightBackend",
    "RenderOutcome",
    "RenderedPage",
    "camoufox_launcher",
]
