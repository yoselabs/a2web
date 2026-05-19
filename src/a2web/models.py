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
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    role: str = "primary"  # "primary" | "nav" | "meta" | "footer"


class OperatorHint(BaseModel):
    """Structured hint about how the fetch could be improved.

    `code` is a stable agent-readable identifier (e.g. `llm_unavailable`,
    `browser_unavailable`, `captcha_redirect`, `cookies_stale`). Agents may
    branch on `code` to take a next action; humans read `message` and `fix`
    for context and remediation. Both audiences are first-class — the field
    landed under the "operator" name historically, not because agents
    shouldn't read it.
    """

    code: str
    message: str
    fix: str | None = None


NextLinkKind = Literal["drilldown", "related", "source"]


class NextLink(BaseModel):
    """One curated "what to fetch next" candidate.

    Returned on `FetchResponse.next_links`. `anchor` and `reason` are
    truncated (not rejected) when over-cap so a misbehaving handler or
    provider can never fail the whole fetch.
    """

    anchor: str = Field(max_length=120)
    url: str
    reason: str = Field(max_length=80)
    kind: NextLinkKind

    @field_validator("anchor", mode="before")
    @classmethod
    def _truncate_anchor(cls, v: object) -> object:
        if isinstance(v, str) and len(v) > 120:
            return v[:120]
        return v

    @field_validator("reason", mode="before")
    @classmethod
    def _truncate_reason(cls, v: object) -> object:
        if isinstance(v, str) and len(v) > 80:
            return v[:80]
        return v


class TokenCounts(BaseModel):
    full: int
    fit: int


class ExtractionMeta(BaseModel):
    """Per-fetch LLM extraction metadata.

    Populated by the v0.4 `ask=` pipeline on `FetchResponse.extraction`.
    Mirrors what `a2web.llm.ExtractionResult` carries, minus the answer
    text (which lives on `FetchResponse.extracted_answer` for ergonomic
    direct access).
    """

    model: str
    template_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    truncated: bool = False


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
    diagnostics_summary: str = ""
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    links: list[Link] = Field(default_factory=list)
    headings: list[Heading] = Field(default_factory=list)
    content_md: str = ""
    fit_md: str | None = None
    operator_hints: list[OperatorHint] = Field(default_factory=list)
    next_links: list[NextLink] = Field(default_factory=list)

    # Defensive flag: `content_md` is external/untrusted content from the
    # fetched URL. Constant False — agents treating tool results as
    # potentially adversarial can branch on this without parsing the
    # in-band HTML-comment markers inside content_md.
    is_user_authored: bool = False
    # v0.4: present only when the caller passed `ask=`. None when ask is unset.
    extracted_answer: str | None = None
    extraction: ExtractionMeta | None = None
    # v0.7: set when the orchestrator rewrote the input URL before tier
    # dispatch (e.g. captcha host → DDG). None when no rewrite occurred.
    # `url` always reflects the URL actually fetched; this field tells the
    # caller what they originally asked for.
    original_url: str | None = None
