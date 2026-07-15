"""BrowserBackend Protocol — what every rendering engine implements.

Domain-free by construction (the `packages/` boundary forbids importing
`a2web.<domain>`): the interface and its value objects carry no
`OperatorHint`/`Verdict`/`Cookie`. The caller (the browser tier) converts the
domain `Cookie` → `BackendCookie` and maps `RenderOutcome` → domain
`Verdict`/`OperatorHint`. Mirrors how `Provider`/`ProviderResponse` stay
domain-free in `llm_extract`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class RenderOutcome(StrEnum):
    """The result class of a `render()` call — the failure channel.

    The tier maps these to domain verdicts/hints: `ok` → trafilatura →
    `ok`/`length_floor`; `timeout` → `Verdict.timeout`; `error` →
    `connection_error` + `browser_internal_error`; `unavailable` →
    `connection_error` + `browser_unavailable`.
    """

    ok = "ok"
    timeout = "timeout"
    error = "error"  # internal navigation/driver error mid-render
    unavailable = "unavailable"  # engine missing / launch failed


@dataclass(frozen=True, slots=True)
class BackendCookie:
    """Engine-neutral cookie. The tier converts the domain `Cookie` to this;
    each backend converts this to its engine's cookie shape.

    `expires=None` means a session cookie. `samesite` is lowercase
    (`"lax"|"strict"|"none"|None`) — the backend titlecases as needed.
    """

    name: str
    value: str
    domain: str
    path: str
    expires: float | None
    secure: bool
    http_only: bool
    samesite: str | None


@dataclass(frozen=True, slots=True)
class RenderedPage:
    """One render result. `detail` is a one-line message on `error`/
    `unavailable` (never a multi-line stack — driver stack traces ride the
    captured-stderr log events). No domain types appear here."""

    outcome: RenderOutcome
    html: str = ""
    final_url: str = ""
    status_code: int = 0
    js_executed: bool = False
    wall_ms: int = 0
    bytes_transferred: int = 0
    detail: str = ""
    # Count of page subresources (XHR/fetch) that returned a challenge status
    # (401/403/429) during render — the walled-API fake-empty signal. The shell
    # can 200 and render an authentic "0 results" while its data API is blocked;
    # this non-text evidence is the only thing that separates that from a true
    # empty. Domain-free (a plain int); the tier maps it to Verdict/hint context.
    subresource_blocks: int = 0


@runtime_checkable
class BrowserBackend(Protocol):
    """A JS-capable rendering engine. Implementations live under this package.

    `render` MUST NOT raise for routine failures (timeout, navigation error,
    missing engine) — it returns a `RenderedPage` with the corresponding
    `outcome`. The backend is the lazily-entered registered resource (async-CM
    protocol), replacing the old `BrowserPool`.
    """

    name: str

    async def render(
        self,
        url: str,
        *,
        cookies: list[BackendCookie],
        budget_s: float,
        js_heavy: bool,
        scroll_to_stable: bool = False,
    ) -> RenderedPage: ...

    async def __aenter__(self) -> BrowserBackend: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...
