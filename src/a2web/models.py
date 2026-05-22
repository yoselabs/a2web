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

from a2kit.packages.formatter.tsv import encode_tsv
from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
)


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

    @model_serializer
    def _as_tuple(self) -> list[int | str]:
        """Render on the wire as a compact `[level, text]` pair.

        Halves the byte cost of the `headings` array versus the
        `{"level": N, "text": "..."}` object form.
        """
        return [self.level, self.text]


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
    """The response envelope returned by the `fetch_raw` tool.

    Field tiers govern what reaches the wire (the serializer regroups /
    drops; the builder populates the model in full for internal callers):

    - Always present: `confidence`.
    - Deviation-only: `status` (dropped when `ok`), `tier` (dropped when
      `raw`), `url` (dropped when it equals the requested URL — absence means
      the fetch landed exactly where the caller asked).
    - Failure-only: `narrative`, `diagnostics_summary` — dropped on success.
    - Debug-only: `started_at`, `total_ms`, `cache`, `tokens`, `diagnostics`
      regroup into a nested `debug` object, present only under `debug=True`.
    - Omitted when empty: `title`, `byline`, `published`, `meta`, `links`,
      `headings`, `operator_hints`, `next_links`, `extraction`,
      `extracted_answer` (and `content_md` on a failed fetch).
    - TSV-rendered: `links` and `next_links` ship as tab-separated blocks.
    """

    url: str
    status: FetchStatus
    tier: str
    confidence: Confidence
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    started_at: datetime | None = None
    total_ms: int | None = None
    tokens: TokenCounts | None = None
    cache: CacheState | None = None

    narrative: str = ""
    diagnostics_summary: str = ""
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    links: list[Link] = Field(default_factory=list)
    headings: list[Heading] = Field(default_factory=list)
    content_md: str = ""
    operator_hints: list[OperatorHint] = Field(default_factory=list)
    next_links: list[NextLink] = Field(default_factory=list)

    # v0.4: present only when the caller passed `ask=`. None when ask is unset.
    extracted_answer: str | None = None
    extraction: ExtractionMeta | None = None

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        tsv: dict[str, str] = {}
        if self.links:
            tsv["links"] = _links_tsv(self.links)
        if self.next_links:
            tsv["next_links"] = _next_links_tsv(self.next_links)
        return _prune_wire(
            handler(self),
            required=_FETCH_REQUIRED_FIELDS,
            tsv=tsv,
            deviation=_WIRE_DEVIATION,
            failure_only=_FAILURE_ONLY_FIELDS,
            debug_fields=_FETCH_DEBUG_FIELDS,
        )


class AskExtraction(BaseModel):
    """Slim per-ask extraction metadata for the wire.

    `truncated` is the one field an agent branches on (the answer may be
    incomplete) and is always present. The observability fields (`model`,
    token counts, cost, latency, cache) are populated only when `ask` was
    called with `debug=True`; otherwise they are None and omitted from the
    wire. The full metadata always reaches LDD events regardless of debug.
    """

    truncated: bool
    model: str | None = None
    template_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    cache_hit: bool | None = None

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        data = handler(self)
        return {k: v for k, v in data.items() if k == "truncated" or v is not None}


# Fields that SHALL never be omitted from the wire, even when falsy
# (`extracted_answer is None` when the LLM was unavailable). `url` / `tier` /
# `status` are NOT here — they are deviation-only (see `_WIRE_DEVIATION`).
_ASK_REQUIRED_FIELDS = frozenset({"confidence", "extracted_answer"})

# `fetch_raw` always-on field. `extracted_answer` is not here — `fetch_raw`
# never runs the LLM, so it is always empty and simply dropped.
_FETCH_REQUIRED_FIELDS = frozenset({"confidence"})

# Fields dropped from the wire on a successful fetch (`status == ok`) — they
# only carry signal when something went wrong.
_FAILURE_ONLY_FIELDS = frozenset({"narrative", "diagnostics_summary"})

# Deviation-only fields: dropped when the value equals the boring default.
# `status` absent → ok; `tier` absent → plain raw fetch.
_WIRE_DEVIATION = {"status": FetchStatus.ok.value, "tier": "raw"}

# Debug-tier fields regrouped into a nested `debug` object on the wire.
_ASK_DEBUG_FIELDS = frozenset({"started_at", "total_ms", "cache", "diagnostics", "extraction"})
_FETCH_DEBUG_FIELDS = frozenset({"started_at", "total_ms", "cache", "tokens", "diagnostics", "extraction"})


def _next_links_tsv(links: list[NextLink]) -> str:
    """Render the next-link candidates as a compact TSV block.

    Columns are `anchor` / `url` / `reason` / `kind`; the `kind` column is
    dropped when every row is `drilldown` (the common handler-derived case)
    and kept when the list mixes kinds.
    """
    columns = ["anchor", "url", "reason"]
    if {lk.kind for lk in links} != {"drilldown"}:
        columns.append("kind")
    return encode_tsv(links, columns=columns)


def _links_tsv(links: list[Link]) -> str:
    """Render the extracted-link list as a compact TSV block.

    Columns are `anchor` / `href` / `role`. `links` is the single largest
    array `fetch_raw` can emit on an aggregator page — TSV over a JSON array
    of objects is the biggest per-call byte saving.
    """
    return encode_tsv(links, columns=["anchor", "href", "role"])


def _prune_wire(
    data: dict[str, object],
    *,
    required: frozenset[str],
    tsv: dict[str, str],
    deviation: dict[str, str],
    failure_only: frozenset[str] = frozenset(),
    debug_fields: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Shared wire-shaping for the `AskResponse` / `FetchResponse` serializers.

    - `required` keys are kept regardless of value.
    - `deviation` maps a field to its boring default; the field is dropped when
      its value equals that default (`status == ok`, `tier == raw`).
    - `failure_only` keys are dropped on a successful response.
    - `debug_fields` keys are pruned of empties and regrouped under a nested
      `debug` object; no `debug` key is emitted when all of them are empty.
    - `tsv` keys are replaced by their pre-rendered TSV string.
    - Remaining keys are dropped when `None` / `""` / `[]` / `{}`.
    """
    # `data` is post-serialization — `status` is already its `.value` string.
    is_ok = data.get("status") == FetchStatus.ok.value
    out: dict[str, object] = {}
    debug: dict[str, object] = {}
    for key, value in data.items():
        is_empty = value is None or value == "" or value == [] or value == {}
        if key in debug_fields:
            if not is_empty:
                debug[key] = value
        elif key in required:
            out[key] = value
        elif key in deviation and value == deviation[key]:
            continue
        elif key in failure_only and is_ok:
            continue
        elif is_empty:
            continue
        elif key in tsv:
            out[key] = tsv[key]
        else:
            out[key] = value
    if debug:
        out["debug"] = debug
    return out


class AskResponse(BaseModel):
    """Lean response envelope for the `ask` tool.

    Distinct from `FetchResponse` (returned by `fetch_raw`). The `ask` wire
    payload carries the extracted answer, not the page. Field tiers:

    - Always present: `confidence`, `extracted_answer`.
    - Deviation-only: `status` (dropped when `ok`), `tier` (dropped when
      `raw`), `url` (dropped when it equals the requested URL).
    - Optional: omitted from the wire when empty/null (`title`, `byline`,
      `published`, `operator_hints`, `next_links`, `meta`).
    - Opt-in grounding: `content_md` + `headings` appear only when the caller
      passed `include_content=True`.
    - Failure-only: `narrative` + `diagnostics_summary` appear only when
      `status != ok`.
    - Debug-only: `started_at`, `total_ms`, `cache`, `diagnostics`,
      `extraction` regroup into a nested `debug` object, present only when the
      caller passed `debug=True`.

    The builder (`build_ask_response`) decides which fields to populate; the
    serializer below drops empties, applies the deviation rules, and regroups
    the debug tier. Required fields are never dropped.
    """

    url: str
    status: FetchStatus
    tier: str
    confidence: Confidence
    extracted_answer: str | None = None

    title: str | None = None
    byline: str | None = None
    published: date | None = None
    operator_hints: list[OperatorHint] = Field(default_factory=list)
    next_links: list[NextLink] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    extraction: AskExtraction | None = None

    content_md: str = ""
    headings: list[Heading] = Field(default_factory=list)

    narrative: str = ""
    diagnostics_summary: str = ""

    started_at: datetime | None = None
    total_ms: int | None = None
    cache: CacheState | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        tsv: dict[str, str] = {}
        if self.next_links:
            tsv["next_links"] = _next_links_tsv(self.next_links)
        return _prune_wire(
            handler(self),
            required=_ASK_REQUIRED_FIELDS,
            tsv=tsv,
            deviation=_WIRE_DEVIATION,
            failure_only=_FAILURE_ONLY_FIELDS,
            debug_fields=_ASK_DEBUG_FIELDS,
        )
