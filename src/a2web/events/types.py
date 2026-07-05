"""Phase-boundary events emitted by the fetch orchestrator.

These typed payloads are passed directly to `await a2kit.log.info(...)`
(no pre-registration step). a2kit resolves each
instance to a `logging.LogRecord`: message = the type name, payload dict on
`record.a2kit_fields`. Handlers (OTel + the wire bridge that a2kit owns)
read them off the record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Verdict


@dataclass(slots=True)
class TierStarted:
    t_ms: int
    step: str
    engine: str | None = None
    host: str | None = None
    proxy: str | None = None


@dataclass(slots=True)
class TierEnded:
    t_ms: int
    step: str
    engine: str | None
    verdict: Verdict
    dur_ms: int
    extra: dict[str, str | int] = field(default_factory=dict)


@dataclass(slots=True)
class StageStarted:
    t_ms: int
    step: str  # "extract" | "gate" | "fit" | "cache_write"


@dataclass(slots=True)
class StageEnded:
    t_ms: int
    step: str
    verdict: Verdict
    dur_ms: int
    extra: dict[str, str | int] = field(default_factory=dict)


@dataclass(slots=True)
class TierHeartbeat:
    """Mid-tier liveness pulse from inside slow tiers (browser, archive).

    Browser tier emits every 2s during page-load wait. Archive tier emits per
    hedged-request boundary. Closes the "silent until timeout" diagnostic
    blind spot — both OTel and humans see "still alive at 22s, 24s..." when
    a tier is taking its time.
    """

    t_ms: int
    step: str  # "browser" | "archive"
    elapsed_in_tier_ms: int
    detail: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class CookiesAttached:
    """Emitted once per fetch when cookies are attached for the request host.

    Carries names + counts but NEVER values — `value` is redacted at the
    emission seam. See `redact_cookie_for_event` in `a2web.cookie_jar`.
    """

    t_ms: int
    host: str
    cookie_count: int
    cookie_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BrowserSubprocessStderr:
    """One captured line of the Camoufox/Playwright driver subprocess's stderr.

    The browser pool redirects the driver's inherited stderr (`sys.stderr`'s
    fileno, captured at spawn by Playwright's transport) into a pipe so raw
    Node.js driver traces — e.g. the `FFPage._onUncaughtError` TypeError on
    JS-heavy SPAs — never reach the operator's terminal. Each captured line
    surfaces here instead. Zero events on the happy path (clean render).
    """

    line: str


@dataclass(slots=True)
class CookiesStale:
    """Emitted at most once per fetch when the cookie mirror is past threshold.

    `age_hours == -1.0` signals "never refreshed". The hint that lands on the
    response is the agent-visibility channel; this event is for operators.
    """

    t_ms: int
    profile: str
    browser: str
    age_hours: float
    threshold_hours: int


Event = TierStarted | TierEnded | StageStarted | StageEnded | TierHeartbeat | CookiesAttached | CookiesStale | BrowserSubprocessStderr
