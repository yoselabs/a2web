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

from a2kit.packages.formatter import PruneEmpty
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
    paid_auth_error = "paid_auth_error"
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
    `browser_unavailable`, `browser_internal_error`, `captcha_redirect`,
    `cookies_stale`). Agents may
    branch on `code` to take a next action; humans read `message` and `fix`
    for context and remediation. Both audiences are first-class — the field
    landed under the "operator" name historically, not because agents
    shouldn't read it.
    """

    code: str
    message: str
    fix: str | None = None
    severity: Literal["info", "critical"] = "info"

    @model_serializer(mode="wrap")
    def _omit_default_severity(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        """Drop `severity` from the wire when it is the default `info`.

        Keeps existing operator-hint snapshots stable — only a `critical`
        hint (e.g. `try_user_browser`) surfaces the new key.
        """
        data = handler(self)
        if data.get("severity") == "info":
            data.pop("severity", None)
        return data


def try_user_browser_hint(url: str) -> OperatorHint:
    """The critical never-silently-miss escalation hint for a walled URL.

    Capability-generic (never names a specific browser product). Imperative:
    the caller must either open the URL in a real browser tool or explicitly
    tell the user the source could not be retrieved. Emitted eagerly by the
    Reddit handler and late (after the tier ladder) for other walled hosts.
    """
    return OperatorHint(
        code="try_user_browser",
        message=(
            f"This URL was NOT retrieved — it is behind an anti-bot / paywall wall ({url}). "
            "You do NOT have this content; do not answer as if you do. You MUST either open it "
            "in a real browser tool (a logged-in browser can pass this wall) OR explicitly tell "
            "the user this source could not be retrieved and what is missing."
        ),
        fix="Open the URL in a real-browser tool and read the page, or report the gap to the user.",
        severity="critical",
    )


def comments_partial_hint(*, loaded: int, total: int) -> OperatorHint:
    """Honest partial-comments signal (reddit-via-zyte content-expectations).

    Informational (not critical): the fetch DID retrieve content — a ranked
    sample — but fewer comments than the thread advertises. Names the loaded
    and total counts so an agent knows it is holding a top-N sample, never the
    complete thread. Pairs with the structured `comments_loaded`/`comments_total`
    fields on the response envelope.
    """
    return OperatorHint(
        code="comments_partial",
        message=(
            f"Loaded the top {loaded} of {total} comments (sorted by top). Deeper/nested replies and "
            "comments beyond the fetch limit were NOT retrieved — this is a ranked sample, not the "
            "complete thread. Do not claim to have every comment."
        ),
        fix="Treat this as a top-ranked sample; to read a specific deeper reply, open the thread in a browser tool.",
        severity="info",
    )


def listing_partial_hint(*, loaded: int, total: int) -> OperatorHint:
    """Honest partial-listing signal (listing-completeness sufficiency axis).

    Informational (not critical): the fetch DID return real records — but fewer
    than the page advertises, because infinite-scroll / lazy-load only
    materialised the first batch. Names the loaded and total counts so an agent
    knows it is holding a truncated sample, never the whole listing. Pairs with
    the structured `items_loaded`/`items_total` fields on the response envelope.
    """
    return OperatorHint(
        code="listing_partial",
        message=(
            f"Parsed {loaded} of {total} listed items — the rest load on scroll / a later page and were "
            "NOT retrieved. This is a partial sample, not the complete listing. For a narrower, complete "
            "set, refine the query (for a search) or open the page in a browser tool."
        ),
        fix="Narrow the search query for fewer, complete results, or open the URL in a browser tool to scroll the full listing.",
        severity="info",
    )


def extraction_empty_hint(*, content_chars: int) -> OperatorHint:
    """Dangerous silent-miss guard: content was fetched but extraction produced
    no answer (never-silently-miss / ADR-0009 at extraction granularity).

    Critical: `ask` fetched `content_chars` of real content yet the LLM
    extraction returned an empty answer — an extraction/parse failure or a model
    that did not follow the answer contract. The caller must NOT read an empty
    answer as "no data on the page"; the data is present but unextracted.
    """
    return OperatorHint(
        code="extraction_empty",
        message=(
            f"Fetched {content_chars} characters of content but extraction produced an EMPTY answer. "
            "This is an extraction/parse failure, not an empty page — do not conclude the page has no "
            "relevant data."
        ),
        fix="Retry the fetch, use `fetch_raw` to inspect the raw content, or rephrase the question.",
        severity="critical",
    )


NextLinkKind = Literal["drilldown", "related", "source", "discussion"]


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


class ContentCandidateWire(BaseModel):
    """One extraction-input candidate as it appears under `debug` (ADR-0005).

    Mirrors the internal `fetcher.ContentCandidate` for the wire: `source`
    names the rung (`trafilatura` / `json_synth` / `record_synth`),
    `content_md` is exactly the rendered block fed into the extractor menu.
    Debug-only — surfaces the menu Haiku saw, so the fix is inspectable
    without changing the default envelope.
    """

    source: str
    content_md: str


# v0.21 — router-shape payload (pydantic mirrors of
# `packages/llm_extract/router_payload.py` boundary types). Closed-enum Literal
# types enforce the prompt's vocabulary at the API edge. Projection from the
# boundary type to the pydantic model happens in `fetcher_response.py`.
StructuralForm = Literal[
    "article",
    "thread",
    "listing",
    "reference",
    "tutorial",
    "changelog",
    "code",
    "product",
    "media",
    "other",
]
Shape = Literal[
    "prose",
    "records",
    "key-value",
    "code",
    "table",
    "discussion",
    "mixed",
]
Genre = Literal[
    "news",
    "encyclopedia",
    "spec",
    "paper",
    "personal",
    "official",
    "community",
]
Obstacle = Literal["paywalled", "blocked", "empty", "error"]


class NextUrl(BaseModel):
    """One curated drilldown URL emitted in the router-shape payload.

    `url` MUST appear verbatim in the page content sent to the model;
    enforcement is best-effort at the seam (model misbehavior shouldn't fail
    the whole fetch). `reason` is the model's question-conditioned justification.
    """

    url: str
    reason: str


class RouterPayload(BaseModel):
    """Router-shape payload emitted by the `extract_router_v1` template.

    Three required fields (`answer`, `structural_form`, `shape`) describe what
    the page IS. Four conditional fields (`genre`, `obstacle`, `ask_here`,
    `try_url`) describe what it's ABOUT plus drilldown hints; the serializer
    on `AskResponse` omits the conditionals from the wire when empty.
    """

    answer: str
    structural_form: StructuralForm
    shape: Shape
    genre: Genre | None = None
    obstacle: Obstacle | None = None
    ask_here: list[str] = Field(default_factory=list)
    try_url: list[NextUrl] = Field(default_factory=list)


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

    # True when the requested URL's content was NOT retrieved (a wall:
    # block_page_detected / anti_bot / paywall). Omitted from the wire when
    # False (see `_prune_wire`); absence therefore means retrieval was complete.
    retrieval_incomplete: bool = False

    # reddit-via-zyte content-expectations: loaded vs authoritative-oracle
    # comment counts for a comment-bearing page. Both None (omitted from the
    # wire) unless a handler measured them. When `comments_total` exceeds
    # `comments_loaded`, a `comments_partial` operator hint accompanies these —
    # the honest "top-N of M" sample signal.
    comments_loaded: int | None = None
    comments_total: int | None = None

    # listing-completeness (sufficiency axis): parsed record count vs the page's
    # advertised item oracle for a listing page. Both None (omitted from the
    # wire) unless the page was a partial listing. When set, `items_total`
    # exceeds `items_loaded` and a `listing_partial` operator hint accompanies
    # them — the honest "N of M items" truncated-sample signal.
    items_loaded: int | None = None
    items_total: int | None = None

    # v0.4: present only when the caller passed `ask=`. None when ask is unset.
    extracted_answer: str | None = None
    extraction: ExtractionMeta | None = None
    # Debug-only (ADR-0005): the multi-source menu fed to the extractor, one
    # entry per candidate. Regrouped under `debug` by the serializer; absent on
    # the default wire. Flat attribute for internal callers (the eval spy reads
    # it); only the wire serializer nests it.
    content_candidates: list[ContentCandidateWire] = Field(default_factory=list)
    # v0.21: populated when `ask=` was passed AND `include_routing=True` AND
    # the extractor returned a parseable router-shape envelope. Carried on
    # FetchResponse so the seam projector (`build_ask_response`) can lift it
    # onto AskResponse. `fetch_raw` never sets this (it does not run the LLM).
    routing: RouterPayload | None = None

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


class AskExtraction(PruneEmpty):
    """Slim per-ask extraction metadata for the wire.

    `truncated` is the one field an agent branches on (the answer may be
    incomplete) and is always present. The observability fields (`model`,
    token counts, cost, latency, cache) are populated only when `ask` was
    called with `debug=True`; otherwise they are None and omitted from the
    wire. The full metadata always reaches log events regardless of debug.

    `PruneEmpty` (a2kit v0.40.1) installs a `model_serializer` that drops
    `None` / `""` / `[]` / `{}` fields; pydantic cascades it through the
    parent `AskResponse._envelope_discipline`. `truncated: bool` is required
    and `False` is not "empty" — so it survives regardless.
    """

    truncated: bool
    model: str | None = None
    template_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    cache_hit: bool | None = None


# Fields that SHALL never be omitted from the wire, even when falsy
# (`answer is None` when the LLM was unavailable). `url` / `tier` / `status`
# are NOT here — they are deviation-only (see `_WIRE_DEVIATION`).
_ASK_REQUIRED_FIELDS = frozenset({"confidence", "answer"})

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
_FETCH_DEBUG_FIELDS = frozenset({"started_at", "total_ms", "cache", "tokens", "diagnostics", "extraction", "content_candidates"})


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
        # Scoped omit-when-False: `retrieval_incomplete` is a bool whose `False`
        # (retrieval complete) is the boring default and must not leak onto the
        # wire. Kept field-scoped so other `False` bools are unaffected.
        if key == "retrieval_incomplete" and value is False:
            is_empty = True
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

    - Always present: `confidence`, `answer`.
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
    answer: str | None = None

    title: str | None = None
    byline: str | None = None
    published: date | None = None
    operator_hints: list[OperatorHint] = Field(default_factory=list)
    next_links: list[NextLink] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=dict)
    extraction: AskExtraction | None = None

    # Mirrors FetchResponse.retrieval_incomplete — true when the URL was walled
    # and not retrieved. Omitted from the wire when False (see `_prune_wire`).
    retrieval_incomplete: bool = False

    # Mirrors FetchResponse — loaded vs oracle comment counts (reddit-via-zyte).
    # Both None (omitted) unless a handler measured them; a shortfall is also
    # flagged by a `comments_partial` operator hint.
    comments_loaded: int | None = None
    comments_total: int | None = None

    # Mirrors FetchResponse — parsed vs advertised item counts for a partial
    # listing (listing-completeness). Both None (omitted) unless the page was a
    # partial listing; a shortfall is flagged by a `listing_partial` hint.
    items_loaded: int | None = None
    items_total: int | None = None

    content_md: str = ""
    headings: list[Heading] = Field(default_factory=list)

    narrative: str = ""
    diagnostics_summary: str = ""

    started_at: datetime | None = None
    total_ms: int | None = None
    cache: CacheState | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    # v0.21 router-shape fields. Required when extraction succeeded;
    # `_envelope_discipline` (the model_serializer below) omits the conditionals
    # (genre / obstacle / ask_here / try_url) when None / empty. All seven fields
    # are absent on the wire when extraction was skipped or the parser failed.
    structural_form: StructuralForm | None = None
    shape: Shape | None = None
    genre: Genre | None = None
    obstacle: Obstacle | None = None
    ask_here: list[str] = Field(default_factory=list)
    try_url: list[NextUrl] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _envelope_discipline(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        # Omit-empty for the 4 conditional router-shape fields lives inside
        # `_prune_wire`'s generic empty-drop path: `genre` / `obstacle` are
        # None when not applicable; `ask_here` / `try_url` are `[]`. The shared
        # helper drops them automatically; the only AskResponse-specific bit is
        # not adding them to `required` so they pass through the empty filter.
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
