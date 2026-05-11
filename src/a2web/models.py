"""Public envelope and diagnostic types for a2web's `fetch` tool.

All types are at module scope (a2kit antipattern #2). The `FetchResponse`
shape is locked here in PR1 — every field comes from `v0.1-response-format.md`
§2 and renaming any of them after MCP clients exist is a breaking change.

The TOON-flavored markdown serializer for the wire format is a *renderer* over
this model, not a different envelope. PR1 lets a2kit's default formatter handle
serialization; the custom renderer ships in a later PR.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Verdict(StrEnum):
    ok = "ok"
    paywall = "paywall"
    block_page_detected = "block_page_detected"
    anti_bot = "anti_bot"
    length_floor = "length_floor"
    content_type_mismatch = "content_type_mismatch"
    connection_error = "connection_error"
    timeout = "timeout"
    not_found = "not_found"
    rate_limited = "rate_limited"
    proxy_unavailable = "proxy_unavailable"
    other = "other"


class FetchStatus(StrEnum):
    ok = "ok"
    failed = "failed"
    partial = "partial"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class CacheState(StrEnum):
    hit = "hit"
    miss = "miss"
    bypass = "bypass"


class Diagnostic(BaseModel):
    """One row of the diagnostics table — a tier or stage step.

    `subsystem` carries the anti-bot family identifier (cloudflare, datadome,
    anubis…) when `verdict == anti_bot`; None otherwise.
    """

    t_ms: int
    step: str
    engine: str | None = None
    host: str | None = None
    proxy: str | None = None
    verdict: Verdict
    subsystem: str | None = None
    dur_ms: int
    extra: dict[str, str | int | float] = Field(default_factory=dict)


class Heading(BaseModel):
    level: int = Field(ge=1, le=6)
    text: str


class Link(BaseModel):
    anchor: str
    href: str


class OperatorHint(BaseModel):
    """Human-readable hint about how an operator could improve fetch outcomes.

    Distinct from the calling-agent flow: the AI agent never reads these to
    decide a next action — they're for the human running a2web.
    """

    code: str
    message: str
    fix: str | None = None


class TokenCounts(BaseModel):
    full: int
    fit: int


class FetchResponse(BaseModel):
    """The single response envelope from the `fetch` tool.

    Field set is locked per `v0.1-response-format.md` §2. Sections that are
    empty in a given response render as omitted in the TOON markdown form;
    they remain typed (default-empty) here so the schema is stable.
    """

    url: str
    status: FetchStatus
    tier: str
    confidence: Confidence
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    started_at: datetime
    total_ms: int
    tokens: TokenCounts | None = None
    cache: CacheState

    narrative: str = ""
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    links: list[Link] = Field(default_factory=list)
    headings: list[Heading] = Field(default_factory=list)
    content_md: str = ""
    fit_md: str | None = None
    operator_hints: list[OperatorHint] = Field(default_factory=list)
