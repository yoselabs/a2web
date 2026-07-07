"""Fetch orchestrator — cache check → tier loop → extract → gate → cache write.

The orchestrator is the only place tier order is encoded. Tiers themselves
are pure-ish (HTTP I/O only); extraction is sync libraries via async
chokepoints; the gate is a pure function. Block pages NEVER enter the
cache (gate verdict gates the write).

State for one fetch lives in a `FetchContext` dataclass. The pipeline is a
sequence of named phase functions that mutate fields on it; the top-level
`_run_pipeline` is a thin coordinator.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from dataclasses import dataclass as _dc
from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal, cast
from urllib.parse import urlparse

import a2kit
import a2kit.log
from a2kit import Lazy

from . import content_expectations
from .actions import Action, EscalateBrowser, EscalatePaid, PlannerCaps, RetryViaArchive, RewriteUrl, decide_next
from .cookie_jar import Cookie, CookieJarResource
from .decision_log import Observation, ObservationKind, resolve_verdict
from .domain import (
    compute_profile_hash,
    is_live_only,
    json_response_fallback,
    json_to_markdown_rows,
    rewrite_captcha_host,
)
from .events import StageEnded, StageStarted, TierEnded, TierStarted
from .events.types import CookiesAttached, CookiesStale
from .fetcher_response import _INCOMPLETE_OBSTACLES, build_response
from .listing_oracle import listing_has_more, listing_oracle
from .llm_resource import LlmExtractorResource
from .models import (
    CacheState,
    Diagnostic,
    ExtractionMeta,
    FetchResponse,
    Heading,
    Link,
    NextLink,
    NextLinkKind,
    OperatorHint,
    Verdict,
    try_user_browser_hint,
)
from .packages.block_detector import LENGTH_FLOOR, looks_like_unrendered_spa
from .packages.block_detector import evaluate as _package_evaluate
from .packages.browser_backends import BrowserBackend
from .packages.content_extract import (
    extract_markdown as _package_extract_markdown,
)
from .packages.content_extract import (
    parse_metadata,
)
from .packages.escalation import EscalationSignal
from .packages.http_cache import CacheRow, SqliteResource
from .packages.json_in_script import (
    extract_json_payloads,
    is_answer_bearing,
    is_json_content_type,
    parse_json_response,
    rank_payloads,
)
from .packages.llm_extract import LlmNextLink, RouterPayload
from .packages.record_extract import Record, RecordSet, extract_records
from .settings import AppSettings
from .state import AppState, ResourceUnavailable, RobustBrowserBackend, unavailable_lazy
from .tiers import REGISTRY, TIER_ORDER, Rendered, Tier, TierResult


@_dc(slots=True)
class _GateResult:
    """Domain-typed wrapper over `packages.block_detector.BlockResult`."""

    verdict: Verdict
    subsystem: str | None = None
    escalation: EscalationSignal | None = None
    # True when the structured-answer exemption is what flipped a bare
    # length_floor to ok — i.e. this ok is a thin page whose only answer source
    # was an answer-bearing structured candidate. Carried so the ask projection
    # can suppress a false `obstacle: empty` incompleteness flag
    # (structured-grounded-completeness).
    promoted_structured: bool = False


_JINA_PAYWALL_STUB_RE = re.compile(r"Target URL returned error 40[13]")
_JINA_STUB_MAX_BODY: int = 2_048
_THIN_BROWSER_MAX_BODY: int = 1_024

# Hosts known to be JS-heavy CSR apps. When the browser tier returns a thin
# 200 OK from one of these, the gate downgrades to length_floor so escalation
# continues (operator can extend via AppSettings.js_heavy_hosts_extra).
_JS_HEAVY_HOSTS_SEED: frozenset[str] = frozenset(
    {
        "x.com",
        "twitter.com",
        "instagram.com",
        "tiktok.com",
        "trendyol.com",
        "aliexpress.com",
    }
)


def js_heavy_hosts(settings: AppSettings | None = None) -> frozenset[str]:
    """Return the union of seed + settings-extra JS-heavy hosts."""
    if settings is None or not settings.js_heavy_hosts_extra:
        return _JS_HEAVY_HOSTS_SEED
    return _JS_HEAVY_HOSTS_SEED | frozenset(h.strip().lower() for h in settings.js_heavy_hosts_extra if h.strip())


def evaluate(
    *,
    content_md: str,
    raw_html: str,
    content_type: str | None,
    tier: str | None = None,
    host: str | None = None,
    settings: AppSettings | None = None,
    is_json: bool = False,
    structured_answer: bool = False,
) -> _GateResult:
    """Run the package's block detector, map BlockVerdict → Verdict.

    Post-process: when `tier == "jina"` and the body carries jina's
    paywall stub markers ("Target URL returned error 401/403"), promote
    the verdict to `Verdict.paywall` so the orchestrator's archive
    escalation fires (see openspec/changes/harsh-test-session-fixes/
    specs/quality-gate/spec.md).
    """
    result = _package_evaluate(content_md=content_md, raw_html=raw_html, content_type=content_type)
    verdict = Verdict(result.verdict.value)
    subsystem = result.subsystem
    escalation = result.escalation

    if tier == "jina" and len(content_md) < _JINA_STUB_MAX_BODY and _JINA_PAYWALL_STUB_RE.search(content_md):
        verdict = Verdict.paywall
        subsystem = "jina_stub"
        escalation = None  # archive playbook handles next step

    if tier == "browser" and len(content_md) < _THIN_BROWSER_MAX_BODY and host and verdict in (Verdict.ok, Verdict.length_floor):
        norm_host = host.lower()
        if norm_host.startswith("www."):
            norm_host = norm_host[4:]
        host_matches = norm_host in js_heavy_hosts(settings)
    else:
        host_matches = False
    if host_matches:
        verdict = Verdict.length_floor
        subsystem = "thin_browser_response"

    # A small-but-complete JSON response (`{"count": 42}`) is a valid answer, not
    # a truncated SPA shell. Exempt JSON from the thin-shell length floor — keyed
    # STRICTLY on the JSON content-type, so HTML shells keep the full floor (the
    # v0.29.0 confabulation guard is untouched).
    if is_json and verdict is Verdict.length_floor:
        verdict = Verdict.ok
        subsystem = None

    # A thin page whose answer lives in answer-bearing structured data (a strong
    # JSON-LD LocalBusiness/Product/…) is small-but-complete, not a truncated
    # shell — mirror the `is_json` promotion. Scoped to the BARE length_floor
    # (`subsystem is None`): a `js_required` / `thin_browser_response` shell keeps
    # its subsystem here and continues escalating even if it embeds a stub
    # payload, so no wall is masked. The `structured_answer` flag is set by the
    # caller from `ContentCandidate.answer_bearing` (strong payloads only).
    promoted_structured = False
    if structured_answer and verdict is Verdict.length_floor and subsystem is None:
        verdict = Verdict.ok
        subsystem = None
        promoted_structured = True

    return _GateResult(
        verdict=verdict, subsystem=subsystem, escalation=escalation, promoted_structured=promoted_structured
    )


@dataclass(slots=True, frozen=True)
class ContentCandidate:
    """One source's bid to fill `FetchContext.content_md`.

    Phase 6 of `fetcher-orchestrator-refactor-v1`: escalators return immutable
    candidates instead of mutating `fc.content_md` in place. The caller
    (`_run_extraction_escalation`) decides which candidate wins via the same
    length / threading policy as before, then assigns once.

    `source` identifies which ladder rung produced the candidate. `next_links`
    is carried for the records source (which doubles as a next-link producer
    for un-handled listing pages).
    """

    source: Literal["trafilatura", "json_synth", "record_synth"]
    content_md: str
    next_links: list[NextLink] = field(default_factory=list)
    # Threaded record renders carry structure trafilatura flattens away — the
    # one non-length quality signal that overrides prose for the display pick.
    is_threaded: bool = False
    # Set by the json_synth rung from `is_answer_bearing(payload)` — a strong
    # structured payload (contact/org/product/…) carries an answer, not chrome.
    # The quality-gate small-but-complete exemption and the sub-floor display
    # pick key on this flag. Prose and record candidates leave it False.
    answer_bearing: bool = False


@_dc(slots=True)
class _ExtractResult:
    """Domain-typed wrapper over `packages.content_extract.ExtractedContent`."""

    content_md: str
    title: str | None
    byline: str | None
    published: date | None
    headings: list[Heading]
    links: list[Link]
    score: float | None


async def extract_markdown(html: str, url: str) -> _ExtractResult:
    """Run package extract, map frozen dataclasses → pydantic Heading/Link."""
    raw = await _package_extract_markdown(html, url)
    return _ExtractResult(
        content_md=raw.content_md,
        title=raw.title,
        byline=raw.byline,
        published=raw.published,
        headings=[Heading(level=h.level, text=h.text) for h in raw.headings],
        links=[Link(anchor=lk.anchor, href=lk.href, role=lk.role) for lk in raw.links],
        score=raw.score,
    )


def _ttl_for(content_type: str | None, settings_obj: object) -> int:
    """Pick a TTL in seconds based on a coarse content-type heuristic."""
    ct = (content_type or "").lower()
    if "html" in ct:
        return getattr(settings_obj, "cache_ttl_article_h", 24) * 3600
    return getattr(settings_obj, "cache_ttl_static_h", 168) * 3600


@dataclass(slots=True)
class FetchContext:
    """Mutable per-fetch state passed between phase functions.

    Replaces the v0.1 pattern of 20+ local variables in `_run_pipeline`.
    Phase functions read and write fields here; the top-level coordinator
    constructs one, runs the phases, and builds the response from it.
    """

    # Inputs (set at construction; not mutated by phases)
    started_at: datetime
    start_perf: float
    profile_hash: str
    sqlite: SqliteResource | None
    bypass_cache: bool

    # URL state (rewritten on after-tier RewriteUrl)
    url: str
    final_url: str
    # The URL the caller actually passed — captured once at fetch() entry,
    # never mutated by captcha or after-tier rewrites. `build_response`
    # compares it against `final_url` to decide whether `url` is wire-worthy.
    requested_url: str = ""

    # Lazy handles for heavy/conditional resources (a2kit v0.36+). Phases that
    # actually need browser or LLM extraction `await fc.browser_backend()` /
    # `await fc.llm_extractor()` to resolve the resource once at the seam.
    # Resources never enter when their consuming phase doesn't fire.
    #
    # Non-optional (Phase 3 of fetcher-orchestrator-refactor-v1): the `fetch()`
    # entrypoint normalizes any `None` caller-kwarg to an `unavailable_lazy(...)`
    # stub before constructing FetchContext, so phases never check for `None` —
    # they `await` uniformly and catch `ResourceUnavailable` to emit the
    # graceful operator hint.
    browser_backend: Lazy[BrowserBackend] = field(
        default_factory=lambda: unavailable_lazy(BrowserBackend, reason="browser_backend not provisioned"),
    )
    # Robust browser rung (CDP) — resolved only on the SECOND browser dispatch
    # (fast rung came back thin/blocked). Separate Lazy seam so it enters only
    # when the robust escalation actually fires.
    browser_robust_backend: Lazy[RobustBrowserBackend] = field(
        default_factory=lambda: unavailable_lazy(RobustBrowserBackend, reason="browser_robust_backend not provisioned"),
    )
    llm_extractor: Lazy[LlmExtractorResource] = field(
        default_factory=lambda: unavailable_lazy(LlmExtractorResource, reason="llm_extractor not provisioned"),
    )
    cookie_jar: Lazy[CookieJarResource] = field(
        default_factory=lambda: unavailable_lazy(CookieJarResource, reason="cookie_jar not provisioned"),
    )

    # Response-shape opt-ins (v0.3 envelope diet)
    include_links: bool = False
    debug: bool = False
    # v0.6 link-role filter — None keeps all roles, otherwise a frozenset of
    # roles to keep. Default keeps only "primary" when links are included.
    link_roles: frozenset[str] | None = frozenset({"primary"})
    # v0.6 untrusted-content envelope: wrap content_md with HTML-comment
    # markers carrying source + fetched_at + an untrusted warning. Defensive
    # cue for agent-side prompt-injection awareness.
    wrap_content: bool = True
    # v0.4: optional LLM extraction question + outputs
    ask: str | None = None
    extracted_answer: str | None = None
    extraction_meta: ExtractionMeta | None = None
    # v0.21 router-shape payload — populated when `include_routing=True` and
    # the extractor returned a parseable router-shape envelope. Boundary type
    # from packages/llm_extract; projected into pydantic at the seam in
    # `fetcher_response.build_response`.
    routing: RouterPayload | None = None
    include_routing: bool = True

    # Body & content state (set by tier loop, escalations append observations)
    body: bytes = b""
    content_type: str = ""
    status_code: int = 0
    tier_used: str = "none"
    etag: str | None = None
    last_modified: str | None = None
    pre_rendered_payload: Rendered | None = None

    # Cache state
    cache_state: CacheState = CacheState.miss
    cached_row: CacheRow | None = None

    # Per-fetch escalation caps
    url_rewrites: int = 0
    archive_dispatches: int = 0
    browser_dispatches: int = 0
    paid_dispatches: int = 0
    # A handler asked for a direct paid site render (TierResult.escalate_to_render):
    # the free ladder was stopped, and the gate/escalate phase dispatches the paid
    # tier straight onto the original URL.
    render_requested: bool = False
    # True when the gate promoted a bare length_floor to ok via the
    # structured-answer exemption — this ok is a thin page answered from
    # structured data only. Suppresses the false `obstacle: empty`
    # retrieval-incomplete flag at the ask projection.
    structured_grounded: bool = False

    # Extraction outputs
    content_md: str = ""
    # The multi-source menu (ADR-0005): every rung that produced output
    # (prose + json_synth + record_synth), collected immutably instead of
    # collapsed to a single length-gated winner. Fed in full to the extractor;
    # `content_md` is the quality-picked display default drawn from it.
    content_candidates: list[ContentCandidate] = field(default_factory=list)
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    meta_dict: dict[str, str] = field(default_factory=dict)

    # Append-only decision log — the single source of truth for the verdict.
    # Phases append Observations; the final verdict is the pure projection
    # `resolve_verdict(observations)`. There is no mutable verdict slot.
    observations: list[Observation] = field(default_factory=list)
    # Diagnostics + operator-hint accumulators — anywhere in the pipeline can append.
    diagnostics: list[Diagnostic] = field(default_factory=list)
    operator_hints: list[OperatorHint] = field(default_factory=list)

    # v0.8 cookies — resolved once per host (re-resolved on URL rewrite). The
    # `cookies` dict feeds curl_cffi's `cookies=` kwarg; `cookies_full` carries
    # the full Cookie objects for the browser tier's `context.add_cookies(...)`
    # shape conversion. Stays empty when `settings.cookie_source == "none"` or
    # when the resolved host has no cookies in the mirror.
    cookies: dict[str, str] = field(default_factory=dict)
    cookies_full: list[Cookie] = field(default_factory=list)
    # Idempotency guard: the staleness operator-hint is appended at most once
    # per fetch, even when the tier loop restarts via RewriteUrl.
    cookies_stale_hint_appended: bool = False
    # Tracks the host we last resolved cookies for, so a URL rewrite triggers
    # re-resolution. Empty string = "not yet resolved this fetch".
    cookies_resolved_for_host: str = ""

    # v0.7 link-discovery: candidates from the winning handler (Tier 1) and
    # from LLM extract (Tier 2). The compose phase folds them into the final
    # response per the four-cell matrix in `link-discovery` spec.
    next_links_handler: list[NextLink] = field(default_factory=list)
    next_links_llm: list[NextLink] = field(default_factory=list)
    # Tool-param off-switch. When False, the final response forces [].
    next_links_enabled: bool = True

    # reddit-via-zyte content-expectations: loaded/oracle comment counts a
    # handler measured (None unless the page carried the concept). Threaded onto
    # the response envelope by `build_response`.
    comments_loaded: int | None = None
    comments_total: int | None = None

    # listing-completeness (sufficiency axis): the parsed record count the
    # detector produced (progress metric — set by `_escalate_via_records`, None
    # on a non-listing page), and the wire counts surfaced only when the listing
    # is partial (oracle > records beyond tolerance). Threaded onto the envelope
    # by `build_response`; the shortfall also appends a `listing_partial` hint.
    record_count: int | None = None
    items_loaded: int | None = None
    items_total: int | None = None
    # Structural "more exists" fallback: set when the listing has no numeric
    # oracle but exposes a pagination / infinite-scroll affordance. `items_loaded`
    # is set (record count) while `items_total` stays None; `build_response`
    # appends a `listing_more` hint instead of the quantified `listing_partial`.
    items_more: bool = False

    # v0.10: caller-supplied cap on content chars sent to the extractor LLM.
    # None = inherit Extractor's default (100_000).
    max_content_chars: int | None = None

    def observe(
        self,
        *,
        kind: ObservationKind,
        source: str,
        verdict: Verdict,
        authoritative: bool = False,
        status_code: int = 0,
        cloudflare: bool = False,
        escalation: EscalationSignal | None = None,
        subsystem: str | None = None,
    ) -> None:
        """Append one immutable observation to the decision log."""
        t_ms = int((time.perf_counter() - self.start_perf) * 1000)
        self.observations.append(
            Observation(
                kind=kind,
                source=source,
                verdict=verdict,
                authoritative=authoritative,
                t_ms=t_ms,
                status_code=status_code,
                cloudflare=cloudflare,
                escalation=escalation,
                subsystem=subsystem,
            ),
        )

    def resolved_verdict(self) -> Verdict:
        """Project the current observation log to a verdict (pure, order-independent)."""
        return resolve_verdict(self.observations)

    def last_gate_outcome(self) -> GateOutcomeProjection | None:
        """Return the most recent gate observation as a frozen projection.

        Pure read against the decision log — no mutable snapshot. Returns
        `None` if the gate hasn't run yet. The Phase-2 replacement for the
        old `fc.gate_verdict` / `fc.gate_subsystem` mutable fields.
        """
        for obs in reversed(self.observations):
            if obs.kind is ObservationKind.gate_outcome:
                return GateOutcomeProjection(
                    verdict=obs.verdict,
                    subsystem=obs.subsystem,
                    escalation=obs.escalation,
                )
        return None


@dataclass(frozen=True, slots=True)
class GateOutcomeProjection:
    """Frozen projection of the most recent gate observation.

    Read-only view returned by `FetchContext.last_gate_outcome()` — keeps
    callers from accidentally mutating decision-log state through a
    pseudo-snapshot.
    """

    verdict: Verdict
    subsystem: str | None
    escalation: EscalationSignal | None


async def fetch(
    url: str,
    *,
    state: AppState,
    browser_backend: Lazy[BrowserBackend] | None = None,
    browser_robust_backend: Lazy[RobustBrowserBackend] | None = None,
    llm_extractor: Lazy[LlmExtractorResource] | None = None,
    cookie_jar: Lazy[CookieJarResource] | None = None,
    include_links: bool = False,
    link_roles: frozenset[str] | None = frozenset({"primary"}),
    wrap_content: bool = True,
    debug: bool = False,
    ask: str | None = None,
    next_links: bool = True,
    max_content_chars: int | None = None,
    include_routing: bool = True,
) -> FetchResponse:
    """Run the v0.1 cascade for one URL.

    Emits typed phase-boundary events via `await a2kit.log.info(EventInstance(...))`
    (stdlib logging). The synchronous log to the `a2kit`
    logger always fires; the optional MCP-wire forward only happens under a tool
    dispatch. Outside a dispatch (eval/systems direct call) the emit still logs —
    no ambient ctx is required.

    `include_links` and `debug` are v0.3 envelope-diet opt-ins (both default
    False). See `FetchResponse` docs.

    `ask` (v0.4) opts into server-side LLM extraction: when set, an LLM
    reads `content_md` and produces an answer string returned on
    `extracted_answer`. v0.7+: SDKs are baseline deps, so graceful only
    when no API key AND no Claude Code OAuth available — `extracted_answer`
    stays None and an operator hint is recorded.
    """
    start_perf = time.perf_counter()
    started_at = datetime.now(UTC)
    requested_url = url  # the caller's input, before any rewrite

    # v0.7: captcha-host pre-routing — Google/Bing search URLs serve captcha
    # pages that pass the length floor. Rewrite to DDG before tier dispatch
    # so callers get useful results. `requested_url` (captured above) keeps
    # the wire honest — `url` surfaces the DDG destination as a deviation.
    # The rewrite counts against `fc.url_rewrites` (capped at 1 per fetch by
    # the playbook) — defense against a captcha rewrite stacking with an
    # after-tier RewriteUrl.
    initial_url_rewrites = 0
    rewritten = rewrite_captcha_host(url)
    if rewritten is not None:
        url = rewritten
        initial_url_rewrites = 1

    profile_hash = compute_profile_hash(state.settings)
    bypass_cache = is_live_only(url, state.settings)
    sqlite = None if bypass_cache else state.sqlite

    # Normalize caller-provided Lazy[T] | None → stub-on-unavailable. This is
    # the single seam where the optional public API meets the non-optional
    # FetchContext contract — phases never see `None` again.
    browser_lazy = (
        browser_backend
        if browser_backend is not None
        else unavailable_lazy(
            BrowserBackend,
            reason="browser_backend not provisioned by caller",
        )
    )
    browser_robust_lazy = (
        browser_robust_backend
        if browser_robust_backend is not None
        else unavailable_lazy(
            RobustBrowserBackend,
            reason="browser_robust_backend not provisioned by caller",
        )
    )
    llm_lazy = (
        llm_extractor
        if llm_extractor is not None
        else unavailable_lazy(
            LlmExtractorResource,
            reason="llm_extractor not provisioned by caller",
        )
    )
    cookie_lazy = (
        cookie_jar
        if cookie_jar is not None
        else unavailable_lazy(
            CookieJarResource,
            reason="cookie_jar not provisioned by caller",
        )
    )

    fc = FetchContext(
        started_at=started_at,
        start_perf=start_perf,
        profile_hash=profile_hash,
        sqlite=sqlite,
        bypass_cache=bypass_cache,
        browser_backend=browser_lazy,
        browser_robust_backend=browser_robust_lazy,
        llm_extractor=llm_lazy,
        cookie_jar=cookie_lazy,
        url=url,
        final_url=url,
        requested_url=requested_url,
        url_rewrites=initial_url_rewrites,
        include_links=include_links,
        link_roles=link_roles,
        wrap_content=wrap_content,
        debug=debug,
        ask=ask,
        next_links_enabled=next_links,
        max_content_chars=max_content_chars,
        include_routing=include_routing,
        cache_state=CacheState.bypass if bypass_cache else CacheState.miss,
    )

    response = await _run_pipeline(fc, state=state)

    # v0.3 envelope diet: apply opt-in gates AT THE WIRE BOUNDARY.
    # `diagnostics_summary` is always populated and carries verdict + timing.
    # v0.6 link-role filter: even when links are included, default to
    # role=primary only — kills nav/footer/aside payload bloat.
    if not fc.include_links:
        response.links = []
    else:
        allowed_roles = fc.link_roles
        if allowed_roles is not None:
            response.links = [lk for lk in response.links if lk.role in allowed_roles]
    if not fc.debug:
        response.diagnostics = []

    return response


# --------------------------------------------------------------------- #
# Event emission helpers
# --------------------------------------------------------------------- #


# Note: typed events emit directly via `await a2kit.log.info(event)`.
# a2kit resolves a dataclass/pydantic instance to a `LogRecord` whose message
# is the type name and whose payload dict rides on `record.a2kit_fields`
# (`dataclasses.asdict` + Enum.value coercion). No flattener needed at this seam.


# --------------------------------------------------------------------- #
# Tier emission helpers — shared by tier loop + escalators
# --------------------------------------------------------------------- #


async def _emit_tier_started(
    *,
    step: str,
    host: str | None,
    start_perf: float,
) -> int:
    """Emit `TierStarted` at the current perf-clock tick; return the relative ms."""
    start_ms = int((time.perf_counter() - start_perf) * 1000)
    await a2kit.log.info(TierStarted(t_ms=start_ms, step=step, host=host))
    return start_ms


async def _emit_tier_ended(
    *,
    step: str,
    engine: str | None,
    verdict: Verdict,
    start_ms: int,
    start_perf: float,
    extra: dict[str, str | int] | None = None,
) -> int:
    """Emit `TierEnded` and return the elapsed `dur_ms` (relative to `start_ms`)."""
    dur_ms = int((time.perf_counter() - start_perf) * 1000) - start_ms
    await a2kit.log.info(
        TierEnded(
            t_ms=start_ms,
            step=step,
            engine=engine,
            verdict=verdict,
            dur_ms=dur_ms,
            extra=extra or {},
        ),
    )
    return dur_ms


# --------------------------------------------------------------------- #
# Cookie resolution + staleness phases (v0.8)
# --------------------------------------------------------------------- #


async def _phase_resolve_cookies(fc: FetchContext, *, state: AppState) -> None:
    """Resolve cookies for the current fetch host into FetchContext.

    No-op when `cookie_source == "none"` or when the cookie_jar Lazy is an
    unavailable stub (caller didn't provision one). Re-resolves when
    `fc.url`'s host has changed since the last call (e.g. after `RewriteUrl`).
    Emits a redacted `CookiesAttached` event on a non-empty resolution.
    """
    if state.settings.cookie_source == "none":
        return
    from urllib.parse import urlparse

    parsed = urlparse(fc.url)
    host = parsed.hostname or ""
    if not host:
        return
    if fc.cookies_resolved_for_host == host:
        return  # already resolved for this host this fetch
    scheme = parsed.scheme or "https"
    path = parsed.path or "/"

    try:
        jar = await fc.cookie_jar()
    except ResourceUnavailable:
        return
    cookies_full = await jar.get_for_host(host, scheme, path)
    fc.cookies_full = cookies_full
    fc.cookies = {c.name: c.value for c in cookies_full}
    fc.cookies_resolved_for_host = host

    if cookies_full:
        t_ms = int((time.perf_counter() - fc.start_perf) * 1000)
        await a2kit.log.info(
            CookiesAttached(
                t_ms=t_ms,
                host=host,
                cookie_count=len(cookies_full),
                cookie_names=[c.name for c in cookies_full],
            ),
        )


def _format_age(age_hours: float | None) -> str:
    if age_hours is None:
        return "never"
    if age_hours < 1:
        return f"{age_hours * 60:.0f}m"
    return f"{age_hours:.0f}h"


async def _phase_cookies_staleness(fc: FetchContext, *, state: AppState) -> None:
    """Append the `cookies_stale` operator hint and log event when stale.

    Idempotent within a fetch: `fc.cookies_stale_hint_appended` flips on the
    first append, preventing a duplicate after `RewriteUrl` restarts.
    """
    if state.settings.cookie_source == "none":
        return
    if fc.cookies_stale_hint_appended:
        return
    try:
        jar = await fc.cookie_jar()
    except ResourceUnavailable:
        return
    info = await jar.staleness()
    if not info.is_stale:
        return
    threshold_h = state.settings.cookie_stale_after_hours
    age_str = _format_age(info.age_hours)
    fc.operator_hints.append(
        OperatorHint(
            code="cookies_stale",
            message=(
                f"Browser cookies last refreshed {age_str} ago; threshold is "
                f"{threshold_h}h. Some sites may treat this session as logged-out."
            ),
            fix="Run `a2web cookies refresh`",
        ),
    )
    t_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.log.info(
        CookiesStale(
            t_ms=t_ms,
            profile=state.settings.cookie_profile,
            browser=str(state.settings.cookie_source),
            age_hours=info.age_hours if info.age_hours is not None else -1.0,
            threshold_hours=threshold_h,
        ),
    )
    fc.cookies_stale_hint_appended = True


# --------------------------------------------------------------------- #
# Archive escalation helper (shared by after-tier + after-gate)
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class _ArchiveOutcome:
    """Result of one archive-tier dispatch — used by `_dispatch_archive`."""

    success: bool
    body: bytes = b""
    content_type: str = ""
    final_url: str = ""
    pre_rendered: Rendered | None = None
    status_code: int = 0


async def _dispatch_archive(
    url: str,
    *,
    state: AppState,
    start_perf: float,
    diagnostics: list[Diagnostic],
) -> _ArchiveOutcome:
    """One-stop archive dispatch — used by both after-tier and after-gate paths.

    Emits TierStarted/TierEnded around the archive fetch, appends a Diagnostic
    only on success (a failed escalation is "tried, didn't help" and should
    not displace the originating verdict), and returns an outcome the caller
    installs into orchestrator state.
    """
    archive_tier = REGISTRY["archive"]
    arch_start_ms = await _emit_tier_started(step="archive", host=_host(url), start_perf=start_perf)
    archive_result = await archive_tier.fetch(url, state=state)
    engine = archive_result.archive_source or "archive"
    arch_dur_ms = await _emit_tier_ended(
        step="archive",
        engine=engine,
        verdict=archive_result.verdict,
        start_ms=arch_start_ms,
        start_perf=start_perf,
        extra={"status_code": archive_result.status_code},
    )
    archive_pre = archive_result.pre_rendered
    if archive_result.verdict != Verdict.ok or archive_pre is None:
        return _ArchiveOutcome(success=False)
    diagnostics.append(
        Diagnostic(
            t_ms=arch_start_ms,
            step="archive",
            engine=engine,
            host=_host(url),
            proxy=None,
            verdict=archive_result.verdict,
            dur_ms=arch_dur_ms,
            extra={"status_code": archive_result.status_code},
        )
    )
    return _ArchiveOutcome(
        success=True,
        body=archive_result.body,
        content_type=archive_result.content_type,
        final_url=archive_result.final_url,
        pre_rendered=archive_pre,
        status_code=archive_result.status_code,
    )


# --------------------------------------------------------------------- #
# Phase functions
# --------------------------------------------------------------------- #


async def _phase_cache_check(fc: FetchContext) -> None:
    """Read the cached row (if cache is enabled and a hit exists)."""
    if fc.sqlite is not None:
        fc.cached_row = await fc.sqlite.get(fc.url, fc.profile_hash)


class _Exec(Enum):
    """Outcome of executing a planner action — drives tier-loop control flow."""

    CONTINUE = "continue"  # advance to the next tier
    RESTART = "restart"  # URL was rewritten — restart the tier loop
    STOP = "stop"  # cascade done — a tier won or archive content installed


def _install_won_tier(
    fc: FetchContext,
    tier_result: TierResult,
    tier_name: str,
    tier: Tier,
) -> None:
    """Install winning tier content onto FetchContext.

    The tier observation is appended separately by the caller before the
    planner is consulted — this function only installs the content payload.
    """
    fc.body = tier_result.body
    fc.content_type = tier_result.content_type
    fc.status_code = tier_result.status_code
    fc.final_url = tier_result.final_url
    fc.tier_used = tier_result.handler_name or (tier.name if hasattr(tier, "name") else tier_name)
    fc.etag = tier_result.headers.get("etag")
    fc.last_modified = tier_result.headers.get("last-modified")
    fc.pre_rendered_payload = tier_result.pre_rendered
    # v0.7 link-discovery: thread Tier-1 candidates from the handler into fc.
    fc.next_links_handler = list(tier_result.next_links)
    # reddit-via-zyte content-expectations: carry a handler's measured counts.
    fc.comments_loaded = tier_result.comments_loaded
    fc.comments_total = tier_result.comments_total


def _install_archive_payload(fc: FetchContext, outcome: _ArchiveOutcome) -> None:
    """Install a tier-loop archive escalation outcome onto FetchContext.

    Runs before `_phase_extract`, so it installs the body only — extraction
    fills `content_md` from `pre_rendered_payload`. Appends the archive's
    winning observation.
    """
    fc.body = outcome.body
    fc.content_type = outcome.content_type
    fc.final_url = outcome.final_url
    fc.tier_used = "archive"
    fc.pre_rendered_payload = outcome.pre_rendered
    fc.status_code = outcome.status_code
    fc.observe(kind=ObservationKind.tier_outcome, source="archive", verdict=Verdict.ok)


def _install_gate_archive(fc: FetchContext, outcome: _ArchiveOutcome) -> None:
    """Install a gate-path archive escalation outcome onto FetchContext.

    Unlike `_install_archive_payload`, this lands after `_phase_extract` has
    run — so it sets the extracted fields directly from the archive's
    pre-rendered payload.
    """
    pre = outcome.pre_rendered
    assert pre is not None  # noqa: S101 — narrowed by the caller
    fc.content_md = pre.content_md
    fc.title = pre.title
    fc.byline = pre.byline
    fc.headings = pre.headings
    fc.body = outcome.body
    fc.content_type = outcome.content_type
    fc.final_url = outcome.final_url
    fc.tier_used = "archive"
    fc.pre_rendered_payload = pre


def _planner_caps(fc: FetchContext) -> PlannerCaps:
    """Snapshot the per-fetch escalation budgets for the planner."""
    return PlannerCaps(
        url_rewrites=fc.url_rewrites,
        archive_dispatches=fc.archive_dispatches,
        browser_dispatches=fc.browser_dispatches,
        paid_dispatches=fc.paid_dispatches,
    )


def _tier_is_cloudflare(tier_result: TierResult) -> bool:
    """True when the tier response came through Cloudflare (server / cf-ray header)."""
    server = tier_result.headers.get("server", "").lower()
    return "cloudflare" in server or "cf-ray" in tier_result.headers


async def _execute_tier_action(
    fc: FetchContext,
    action: Action,
    tier_result: TierResult,
    tier_name: str,
    tier: Tier,
    *,
    state: AppState,
) -> _Exec:
    """Execute a planner action inside the tier loop; report loop control flow.

    `RewriteUrl` restarts the loop (cap 1). `RetryViaArchive` dispatches the
    archive tier (cap 1) and stops on success. Otherwise a winning tier
    installs its content and stops; a failed tier continues to the next.
    """
    if isinstance(action, RewriteUrl):
        fc.url_rewrites += 1
        fc.url = action.new_url
        fc.final_url = fc.url
        fc.cached_row = await fc.sqlite.get(fc.url, fc.profile_hash) if fc.sqlite is not None else None
        return _Exec.RESTART

    if isinstance(action, RetryViaArchive):
        fc.archive_dispatches += 1
        outcome = await _dispatch_archive(
            action.url,
            state=state,
            start_perf=fc.start_perf,
            diagnostics=fc.diagnostics,
        )
        if outcome.success:
            _install_archive_payload(fc, outcome)
            return _Exec.STOP
        # Archive failed — fall through to the win / continue decision.

    if tier_result.verdict is Verdict.ok:
        _install_won_tier(fc, tier_result, tier_name, tier)
        return _Exec.STOP
    return _Exec.CONTINUE


async def _phase_tier_loop(fc: FetchContext, *, state: AppState) -> None:
    """Walk TIER_ORDER, dispatch each tier, run after-tier actions, until one wins or all fail.

    Supports two interruptions of the linear flow:
    - `RewriteUrl` from after-tier action → restart the loop with the new URL (cap=1).
    - `RetryViaArchive` from after-tier action → out-of-band archive dispatch (cap=1).
    """
    proxy_pool = state.proxy_pool

    # v0.8: resolve cookies for the current host before any tier dispatch.
    # No-op when cookie_source == "none" or no jar was provisioned.
    await _phase_resolve_cookies(fc, state=state)

    while True:
        restart_loop = False
        # If a previous iteration rewrote the URL to a new host, re-resolve.
        await _phase_resolve_cookies(fc, state=state)
        for tier_name in TIER_ORDER:
            tier = REGISTRY[tier_name]
            tier_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)

            conditional_extras: dict[str, str] | None = None
            if fc.cached_row is not None:
                conditional_extras = {}
                if fc.cached_row.etag:
                    conditional_extras["etag"] = fc.cached_row.etag
                if fc.cached_row.last_modified:
                    conditional_extras["last_modified"] = fc.cached_row.last_modified

            handle = proxy_pool.acquire(_host(fc.url) or "", tier_name)
            if handle is None:
                fc.diagnostics.append(
                    Diagnostic(
                        t_ms=tier_start_ms,
                        step=tier_name,
                        engine=None,
                        host=_host(fc.url),
                        proxy=None,
                        verdict=Verdict.proxy_unavailable,
                        dur_ms=0,
                        extra={"reason": "all_proxies_dead_required"},
                    )
                )
                fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.proxy_unavailable)
                continue

            await a2kit.log.info(TierStarted(t_ms=tier_start_ms, step=tier_name, host=_host(fc.url)))

            tier_result = await tier.fetch(
                fc.url,
                state=state,
                proxy_url=handle.proxy_url,
                conditional_extras=conditional_extras,
                cookies=fc.cookies,
                cookies_full=fc.cookies_full,
            )

            # Silent skip — no diagnostic row
            if tier_result.no_match or tier_result.skipped:
                continue

            proxy_pool.report(
                handle,
                success=tier_result.verdict not in (Verdict.proxy_unavailable, Verdict.connection_error, Verdict.timeout),
            )

            tier_dur_ms = await _emit_tier_ended(
                step=tier_result.handler_name or tier_name,
                engine="curl_cffi" if tier_name == "raw" else None,
                verdict=tier_result.verdict,
                start_ms=tier_start_ms,
                start_perf=fc.start_perf,
                extra={
                    "status_code": tier_result.status_code,
                    "route.proxy_id": handle.proxy_id,
                    "route.matched_rule": str(handle.matched_rule_index) if handle.matched_rule_index is not None else "none",
                },
            )

            # Conditional 304 → reuse cached body. Distinct return path (no
            # after-tier action, no further tiers, no extract/gate ahead).
            if tier_result.status_code == 304 and fc.cached_row is not None and tier_result.conditional_hit:
                fc.body = fc.cached_row.body
                fc.content_type = fc.cached_row.content_type or "text/html"
                fc.status_code = 200  # logical hit
                fc.cache_state = CacheState.hit
                fc.etag = fc.cached_row.etag
                fc.last_modified = fc.cached_row.last_modified
                fc.tier_used = tier_name
                fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.ok)
                fc.diagnostics.append(
                    Diagnostic(
                        t_ms=tier_start_ms,
                        step=tier_name,
                        engine="curl_cffi",
                        host=_host(fc.url),
                        proxy=handle.proxy_id,
                        verdict=Verdict.ok,
                        dur_ms=tier_dur_ms,
                        extra={"conditional_hit": "true"},
                    )
                )
                return

            fc.diagnostics.append(
                Diagnostic(
                    t_ms=tier_start_ms,
                    step=tier_name,
                    engine="curl_cffi" if tier_name == "raw" else None,
                    host=_host(tier_result.final_url),
                    proxy=handle.proxy_id,
                    verdict=tier_result.verdict,
                    dur_ms=tier_dur_ms,
                    extra={"status_code": tier_result.status_code},
                )
            )

            # Escalate to a paid site render: a converting handler's rewritten
            # fetch failed (HN's Algolia API), or a walled surface (Reddit
            # search 403) can only be read by rendering the real page. The
            # diagnostic above records the failed attempt; here we log a
            # NON-authoritative observation, flag the fetch for a direct paid
            # render, and STOP the free ladder — raw/jina would get fooled by the
            # SPA shell (which can exceed the length floor) or the block page. The
            # gate/escalate phase dispatches the paid tier onto the original URL.
            if tier_result.escalate_to_render:
                fc.observe(
                    kind=ObservationKind.tier_outcome,
                    source=tier_result.handler_name or tier_name,
                    verdict=tier_result.verdict,
                    authoritative=False,
                    status_code=tier_result.status_code,
                    cloudflare=False,
                )
                fc.render_requested = True
                return  # stop the free ladder; the paid render happens in gate/escalate

            # Append the tier observation BEFORE consulting the planner, so
            # `decide_next` sees the full decision log; then execute its action.
            authoritative = tier_name == "site_handler" and tier_result.verdict is Verdict.not_found
            fc.observe(
                kind=ObservationKind.tier_outcome,
                source=tier_result.handler_name or tier_name,
                verdict=tier_result.verdict,
                authoritative=authoritative,
                status_code=tier_result.status_code,
                cloudflare=_tier_is_cloudflare(tier_result),
            )
            # Propagate a handler-set operator hint into fc so it reaches the
            # response. Previously only the browser escalation consumed
            # `TierResult.operator_hint`; site handlers (e.g. reddit's eager
            # `try_user_browser`) had no path to the wire.
            if tier_result.operator_hint is not None:
                fc.operator_hints.append(tier_result.operator_hint)
            action = decide_next(fc.observations, url=fc.url, caps=_planner_caps(fc))
            executed = await _execute_tier_action(fc, action, tier_result, tier_name, tier, state=state)
            if executed is _Exec.RESTART:
                restart_loop = True
                break  # break inner for; while True restarts
            if executed is _Exec.STOP:
                return
            # _Exec.CONTINUE → next tier

        if not restart_loop:
            return


async def _phase_extract(fc: FetchContext) -> None:
    """Run extraction on `body` (or use pre-rendered handler output)."""
    extract_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    raw_html = fc.body.decode("utf-8", errors="replace") if fc.body else ""

    if fc.pre_rendered_payload is not None:
        # Site handler / archive / browser already produced markdown; skip trafilatura.
        fc.content_md = fc.pre_rendered_payload.content_md
        fc.title = fc.pre_rendered_payload.title
        fc.byline = fc.pre_rendered_payload.byline
        fc.headings = fc.pre_rendered_payload.headings
        return

    # JSON response body (json-endpoint-direct-routing): the raw tier now wins on
    # JSON (Verdict.ok), so the body lands here. Synthesize it — trafilatura
    # produces nothing on JSON, and escalating to the jina HTML reader mangles it
    # into a false length_floor. Reuse the JSON-in-script synthesis; an
    # unrecognized shape falls back to the capped JSON text so a valid payload is
    # never lost. Installing pre_rendered_payload skips the gate's content-type
    # guard, exactly like a handler's pre-rendered result.
    if fc.body and is_json_content_type(fc.content_type):
        json_text = fc.body.decode("utf-8", errors="replace")
        json_payload = parse_json_response(json_text)
        if json_payload is not None:
            md = json_to_markdown_rows(json_payload) or json_response_fallback(json_payload.data)
            fc.content_md = md
            fc.pre_rendered_payload = Rendered(content_md=md)
            fc.diagnostics.append(
                Diagnostic(
                    t_ms=extract_dur_start,
                    step="json_response",
                    engine="json_synth",
                    host=None,
                    proxy=None,
                    verdict=Verdict.ok,
                    dur_ms=int((time.perf_counter() - fc.start_perf) * 1000) - extract_dur_start,
                    extra={"chars": len(md)},
                )
            )
            return
        # Content-type declared JSON but the body did not parse — fall through to
        # normal handling rather than fabricating content.

    if not (fc.body and fc.resolved_verdict() is Verdict.ok):
        return

    await a2kit.log.info(StageStarted(t_ms=extract_dur_start, step="extract"))
    extract_result = await extract_markdown(raw_html, fc.final_url)
    fc.content_md = extract_result.content_md
    fc.title = extract_result.title
    fc.byline = extract_result.byline
    fc.published = extract_result.published
    fc.headings = extract_result.headings
    fc.links = extract_result.links
    fc.meta_dict = parse_metadata(raw_html)
    await _run_extraction_escalation(fc, raw_html=raw_html)
    _phase_listing_completeness(fc, raw_html=raw_html)
    extract_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - extract_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=extract_dur_start,
            step="extract",
            engine="trafilatura",
            host=None,
            proxy=None,
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        )
    )
    await a2kit.log.info(
        StageEnded(
            t_ms=extract_dur_start,
            step="extract",
            verdict=Verdict.ok,
            dur_ms=extract_dur_ms,
            extra={"chars": len(fc.content_md)},
        ),
    )


async def _run_extraction_escalation(fc: FetchContext, *, raw_html: str) -> None:
    """Collect every structured-extraction source into the menu (ADR-0005).

    No single-winner selection and no value-blind length proxy (retired —
    was: a source replaced `content_md` only when its render was *longer*,
    so a short-but-correct payload silently lost, and a longer *wrong* one
    clobbered the answer-bearing content). Instead: trafilatura prose plus
    every rung that produced output are collected immutably into
    `fc.content_candidates` (fixed order prose → json_synth → record_synth).
    The extractor is fed the whole menu; the wire `content_md` is the
    quality-picked display default (threaded records, else prose, else first
    structured — never the longest). Each rung still self-gates on its own
    preconditions, so a clean article yields only the prose candidate and
    the cascade still falls through to the browser tier.
    """
    candidates: list[ContentCandidate] = []
    if fc.content_md:
        candidates.append(ContentCandidate(source="trafilatura", content_md=fc.content_md))
    candidates.extend(await _escalate_via_json(fc, raw_html=raw_html))
    record_candidate = await _escalate_via_records(fc, raw_html=raw_html)
    if record_candidate is not None:
        candidates.append(record_candidate)

    fc.content_candidates = candidates
    fc.content_md = _pick_display_candidate(candidates)
    for cand in candidates:
        if cand.next_links:
            fc.next_links_handler = cand.next_links
            break


def _phase_listing_completeness(fc: FetchContext, *, raw_html: str) -> None:
    """Sufficiency check — is a fetched listing complete, or a truncated sample?

    Runs after record extraction (listing-completeness Slice 1). When the page
    is a listing (`fc.record_count` set by `_escalate_via_records`) and an item
    oracle (the advertised total) exceeds the parsed record count beyond
    tolerance, surface an honest `listing_partial` signal plus the structured
    `items_loaded`/`items_total` counts — so the caller can never mistake an
    infinite-scroll sample for the whole listing (ADR-0009 on the sufficiency
    axis). Pure verdict — no fetching; the bounded scroll-to-complete action is
    a later slice.

    Silent when: the page is not a listing (`record_count is None`); the count
    meets the oracle within tolerance (`assess` → `ready`); or there is neither
    a numeric oracle nor a structural "more exists" affordance. A
    positive-oracle/zero-record `fail` is the presence axis — left to the
    obstacle/wall machinery.

    Two evidence paths, numeric-first: a quantified oracle drives the exact
    `listing_partial` signal (`items_loaded` + `items_total`); absent a count, a
    pagination / infinite-scroll affordance drives the unquantified
    `listing_more` fallback (`items_loaded` set, `items_total` unknown). The
    numeric oracle is authoritative — when present, the structural affordance is
    ignored (a leftover "next" on a complete last page is not a truncation).
    """
    if fc.record_count is None:
        return
    total = listing_oracle(raw_html)
    if total is not None:
        if content_expectations.assess(loaded=fc.record_count, total=total) != "partial":
            return
        # Flag the partial state; the `listing_partial` hint is appended by
        # `build_response` from these fields, so a later scroll-to-complete
        # (Slice 2) can clear the signal simply by nulling them.
        fc.items_loaded = fc.record_count
        fc.items_total = total
        return
    # No numeric oracle — fall back to the structural affordance. `items_total`
    # stays None (unknown); `build_response` emits `listing_more` off `items_more`.
    if listing_has_more(raw_html):
        fc.items_loaded = fc.record_count
        fc.items_more = True


def _pick_display_candidate(candidates: list[ContentCandidate]) -> str:
    """Wire `content_md` default — preserves the pre-ADR-0005 selection.

    The envelope decision (signed off 2026-06-07) is that the DEFAULT wire is
    unchanged: only the extractor's *input* becomes the menu. So this keeps the
    legacy rule byte-for-byte — `json_synth` replaces prose when longer; else a
    record set replaces when threaded OR longer; else prose — so parsers and
    change #2's record-projection wire gate see no change. The full menu still
    reaches Haiku via `assemble_menu`; the retired length proxy lives ONLY here
    now (a display heuristic), no longer gating what the extractor sees.
    """
    prose = next((c for c in candidates if c.source == "trafilatura"), None)
    prose_md = prose.content_md if prose is not None else ""
    # Sub-floor prose is a thin nav/footer fragment. When a strong structured
    # candidate carries the answer, surface it for display — so `fetch_raw`
    # (which returns only `content_md`, not the extractor menu) yields the
    # answer, not the fragment. Above-floor prose keeps the legacy length pick.
    if len(prose_md) < LENGTH_FLOOR:
        answer_c = next((c for c in candidates if c.answer_bearing), None)
        if answer_c is not None:
            return answer_c.content_md
    json_c = next((c for c in candidates if c.source == "json_synth"), None)
    if json_c is not None and len(json_c.content_md) > len(prose_md):
        return json_c.content_md
    rec = next((c for c in candidates if c.source == "record_synth"), None)
    if rec is not None and (rec.is_threaded or len(rec.content_md) > len(prose_md)):
        return rec.content_md
    if prose_md:
        return prose_md
    other = next((c for c in candidates if c.content_md), None)
    return other.content_md if other is not None else ""


# Static, content-free section labels. Byte-stable so the assembled menu —
# which IS the extractor's prompt-cache prefix (`cache_prefix = {content}`) —
# is identical across different asks on one fetched page (ADR-0005 D2).
_MENU_LABELS: dict[str, str] = {
    "trafilatura": "## source: prose",
    "json_synth": "## source: structured (json)",
    "record_synth": "## source: structured (records)",
}


def assemble_menu(candidates: list[ContentCandidate]) -> str:
    """Assemble the multi-source extractor input - the menu (ADR-0005 D1-D4).

    Pure function of the candidate list: coarse subset-suppression (drop a
    candidate whose normalized text is a strict substring of another's, and
    exact duplicates), then deterministic concatenation with static labels in
    priority order (prose, json, records). Records render last, so the
    extractor's downstream tail-truncation cap drops the lowest-priority
    source first (D3) — no separate cap pass here, keeping the menu byte-stable
    across asks (D2). No timestamps / counts / identity / dict-order.
    """
    blocks: list[str] = []
    for cand in _suppress_subsets(candidates):
        if not cand.content_md:
            continue
        label = _MENU_LABELS.get(cand.source, f"## source: {cand.source}")
        blocks.append(f"{label}\n\n{cand.content_md}")
    return "\n\n".join(blocks)


def _normalize_ws(text: str) -> str:
    """Whitespace-collapsed form for robust substring comparison."""
    return " ".join(text.split())


def _suppress_subsets(candidates: list[ContentCandidate]) -> list[ContentCandidate]:
    """Drop candidates that are a strict substring (or exact dup) of another.

    Guards the 3-7x duplication when the same payload appears across
    microdata / og / ld_json / records. Coarse only - semantic dedup is the
    LLM's job (ADR-0003). Pure + order-preserving.
    """
    texts = [_normalize_ws(c.content_md) for c in candidates]
    kept: list[ContentCandidate] = []
    seen: set[str] = set()
    for i, (norm, cand) in enumerate(zip(texts, candidates, strict=True)):
        if not norm or norm in seen:
            continue
        if any(j != i and norm != texts[j] and norm in texts[j] for j in range(len(texts))):
            continue
        kept.append(cand)
        seen.add(norm)
    return kept


async def _escalate_via_json(fc: FetchContext, *, raw_html: str) -> list[ContentCandidate]:
    """Menu source — embedded JSON (incl. JSON-LD).

    Returns one `ContentCandidate` per *renderable* payload, in rank order —
    NOT just the top-ranked one (ADR-0005: collapsing the JSON source to a
    single ranked payload, then `break`, was the same value-blind single-source
    sin one level down; a non-top-ranked payload could hold the answer). No
    length gate. Duplicate renders are suppressed. The display pick takes the
    first (top-ranked) candidate, so the wire `content_md` stays legacy-stable;
    the full set reaches the extractor via the menu. Pure function — emits log
    telemetry, does NOT mutate `fc.content_md`.
    """
    t_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.log.info(StageStarted(t_ms=t_ms, step="json_synth"))
    payloads = extract_json_payloads(raw_html)
    candidates: list[ContentCandidate] = []
    seen: set[str] = set()
    for payload in rank_payloads(payloads):
        rendered = json_to_markdown_rows(payload)
        if rendered and rendered not in seen:
            seen.add(rendered)
            candidates.append(
                ContentCandidate(
                    source="json_synth",
                    content_md=rendered,
                    answer_bearing=is_answer_bearing(payload),
                )
            )
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - t_ms
    outcome = "no_payloads" if not payloads else ("no_synth" if not candidates else "collected")
    await a2kit.log.info(
        StageEnded(
            t_ms=t_ms,
            step="json_synth",
            verdict=Verdict.ok,
            dur_ms=dur_ms,
            extra={"outcome": outcome, "payloads": len(candidates)},
        )
    )
    return candidates


async def _escalate_via_records(fc: FetchContext, *, raw_html: str) -> ContentCandidate | None:
    """Menu source — structural record detection.

    Returns a `ContentCandidate` (with `next_links` + the threaded flag)
    whenever the detector produces a record set — no length gate (ADR-0005).
    Pure function — no mutation of `fc.content_md` / `fc.next_links_handler`.
    """
    t_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.log.info(StageStarted(t_ms=t_ms, step="record_synth"))
    record_set = extract_records(raw_html, base_url=fc.final_url or "")
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - t_ms
    if record_set is not None:
        synthetic = record_set.to_markdown()
        if synthetic:
            # Promote the parsed record count (previously logged and discarded)
            # onto fc as the listing-completeness progress metric.
            fc.record_count = len(record_set.records)
            next_links = _records_to_next_links(record_set, page_url=fc.final_url or "")
            await a2kit.log.info(
                StageEnded(
                    t_ms=t_ms,
                    step="record_synth",
                    verdict=Verdict.ok,
                    dur_ms=dur_ms,
                    extra={
                        "outcome": "collected",
                        "records": len(record_set.records),
                        "threaded": record_set.is_threaded,
                    },
                )
            )
            return ContentCandidate(source="record_synth", content_md=synthetic, next_links=next_links, is_threaded=record_set.is_threaded)
    outcome = "no_records" if record_set is None else "no_synth"
    await a2kit.log.info(StageEnded(t_ms=t_ms, step="record_synth", verdict=Verdict.ok, dur_ms=dur_ms, extra={"outcome": outcome}))
    return None


# An anchor that reads like a comment count — "12 comments", "1 comment".
_COMMENT_COUNT_RE = re.compile(r"\b\d+\s*comments?\b", re.IGNORECASE)
# Archive-mirror hosts whose links shadow the discussed page in a record's
# link set — skipped as next_links candidates.
_ARCHIVE_MIRROR_HOSTS = frozenset(
    {
        "web.archive.org",
        "archive.org",
        "ghostarchive.org",
        "archive.ph",
        "archive.today",
        "archive.is",
    }
)


def _is_archive_mirror(url: str) -> bool:
    """True when `url` points at a known archive-mirror host."""
    host = (urlparse(url).hostname or "").lower()
    return host in _ARCHIVE_MIRROR_HOSTS or host.endswith(".archive.org")


def _record_discussion_link(record: Record, page_host: str) -> tuple[str, str] | None:
    """A record's discussion permalink — a same-host link whose anchor reads
    like a comment count (`"N comments"`). `None` when the record carries no
    such link (a plain catalog row with only a source link)."""
    for anchor, url in record.links:
        if not _COMMENT_COUNT_RE.search(anchor):
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host or host == page_host:
            return (anchor, url)
    return None


def _records_to_next_links(record_set: RecordSet, *, page_url: str) -> list[NextLink]:
    """Domain seam — convert detected records into `NextLink` candidates.

    Catalog-only: a threaded record set is a conversation already inline on
    the page, not a set of drilldown targets, so it emits nothing. Each flat
    record emits up to two candidates — a `source` link (its heading link, the
    discussed page) and a `discussion` link (a same-host comment-count
    permalink). Candidates are deduplicated by URL and archive-mirror hosts
    are skipped.
    """
    if record_set.is_threaded:
        return []
    page_host = (urlparse(page_url).hostname or "").lower()
    out: list[NextLink] = []
    seen: set[str] = set()
    for record in record_set.records:
        candidates: tuple[tuple[tuple[str, str] | None, NextLinkKind, str], ...] = (
            (record.heading_link, "source", "discussed page"),
            (_record_discussion_link(record, page_host), "discussion", "discussion thread"),
        )
        for link, kind, reason in candidates:
            if link is None:
                continue
            anchor, url = link
            if url in seen or _is_archive_mirror(url):
                continue
            seen.add(url)
            out.append(NextLink(anchor=anchor[:120] or url, url=url, reason=reason, kind=kind))
    return out


async def _phase_gate_and_escalate(fc: FetchContext, *, state: AppState) -> None:
    """Run the gate; on signals, escalate to browser or archive (each capped to 1)."""
    # Forced site render (escalate_to_render): a converting/walled handler asked
    # to render the original URL directly. Go STRAIGHT to the paid tier (Zyte
    # browserHtml) — the free ladder gets fooled by SPA shells / block pages, and
    # the own-browser is unreliable on them. On success the paid content installs
    # and is gated below like any other; if no paid tier is keyed, `_escalate_paid`
    # is a no-op and the empty body falls through to the never-silently-miss hint.
    if fc.render_requested and fc.pre_rendered_payload is None and fc.paid_dispatches < 1:
        await _escalate_paid(fc, state=state)
        # The render was our only route to this page (the free tiers were stopped).
        # If it produced nothing — no paid tier keyed, or the paid tier failed —
        # this is a loud miss: emit the critical never-silently-miss hint.
        if fc.pre_rendered_payload is None and not _has_browser_hint(fc):
            fc.operator_hints.append(try_user_browser_hint(fc.final_url))

    if not (fc.body and fc.resolved_verdict() is Verdict.ok):
        return

    gate_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.log.info(StageStarted(t_ms=gate_dur_start, step="gate"))

    # Pre-rendered handler results carry application/json bodies; skip the
    # html/content-type guard for them — block-page regexes still run on the
    # rendered markdown and length floor catches truly empty results.
    is_pre_rendered = fc.pre_rendered_payload is not None
    gate_content_type = None if is_pre_rendered else fc.content_type
    gate_raw_html = fc.content_md if is_pre_rendered else (fc.body.decode("utf-8", errors="replace") if fc.body else "")
    # A JSON response body is pre-rendered above, so `gate_content_type` is None;
    # thread the JSON-ness explicitly so the gate exempts a short JSON body from
    # the length floor (keyed on the original `fc.content_type`).
    gate_result = evaluate(
        content_md=fc.content_md,
        raw_html=gate_raw_html,
        content_type=gate_content_type,
        tier=fc.tier_used,
        host=urlparse(fc.final_url).hostname if fc.final_url else None,
        settings=state.settings,
        is_json=is_json_content_type(fc.content_type),
        structured_answer=any(c.answer_bearing for c in fc.content_candidates),
    )
    if gate_result.promoted_structured:
        fc.structured_grounded = True
    gate_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - gate_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=gate_dur_start,
            step="gate",
            engine="block_detector",
            host=None,
            proxy=None,
            verdict=gate_result.verdict,
            subsystem=gate_result.subsystem,
            dur_ms=gate_dur_ms,
            extra={},
        )
    )
    await a2kit.log.info(
        StageEnded(t_ms=gate_dur_start, step="gate", verdict=gate_result.verdict, dur_ms=gate_dur_ms),
    )
    fc.observe(
        kind=ObservationKind.gate_outcome,
        source="gate",
        verdict=gate_result.verdict,
        escalation=gate_result.escalation,
        subsystem=gate_result.subsystem,
    )

    # v0.7: search-engine captcha escape — block detector flagged a Google/Bing
    # captcha page that slipped past `rewrite_captcha_host`. Surface an
    # actionable operator hint instead of just an opaque `block_page_detected`.
    if gate_result.subsystem == "captcha_redirect":
        fc.operator_hints.append(
            OperatorHint(
                code="captcha_redirect",
                message="Search engine returned a captcha page; consider DDG/Brave directly.",
                fix="https://duckduckgo.com/html/?q=<your-query>",
            )
        )

    # Planner-driven escalation. Consult `decide_next` over the decision log,
    # execute its action, repeat until it says Continue. Each escalation is
    # capped at one dispatch, so the loop terminates.
    while True:
        action = decide_next(fc.observations, url=fc.final_url, caps=_planner_caps(fc))
        if isinstance(action, EscalateBrowser):
            await _escalate_browser(fc, state=state)
        elif isinstance(action, RetryViaArchive):
            fc.archive_dispatches += 1
            outcome = await _dispatch_archive(
                action.url,
                state=state,
                start_perf=fc.start_perf,
                diagnostics=fc.diagnostics,
            )
            if outcome.success and outcome.pre_rendered is not None:
                _install_gate_archive(fc, outcome)
                _regate_after_escalation(fc)
        elif isinstance(action, EscalatePaid):
            await _escalate_paid(fc, state=state)
        else:
            break  # Continue (or a URL rewrite — not used post-gate)

    # Late never-silently-miss escalation: the tier + escalation ladder is now
    # exhausted. If the fetch ended on a terminal wall, tell the caller —
    # loudly — that the URL was not retrieved and only a real browser can pass.
    # This is the safety net that catches every host, including Reddit shapes
    # the site handler does NOT claim (e.g. `/user/`, `/wiki/`), which fall
    # through to raw/jina and hit the wall with no eager hint. The
    # `_has_browser_hint` dedup guarantees we never double-emit when the Reddit
    # handler already attached its eager hint.
    if fc.resolved_verdict() in _WALL_VERDICTS and not _has_browser_hint(fc):
        fc.operator_hints.append(try_user_browser_hint(fc.final_url))


# Terminal "walled" verdicts: the content was not retrieved and only a real
# (logged-in) browser can pass. Drives the never-silently-miss escalation.
_WALL_VERDICTS = (Verdict.block_page_detected, Verdict.anti_bot, Verdict.paywall)


def _has_browser_hint(fc: FetchContext) -> bool:
    return any(h.code == "try_user_browser" for h in fc.operator_hints)


def _regate_after_escalation(fc: FetchContext) -> None:
    """Re-evaluate the gate on freshly-installed escalation content.

    Used after both browser and gate-path archive installs. Appends a
    gate-outcome observation to the decision log — the new observation IS
    the new gate state (no mutable snapshot to keep in sync). The
    pre-rendered markdown plays both the `content_md` and `raw_html`
    roles — the underlying body is no longer the discriminator at this
    point in the pipeline.
    """
    regate = evaluate(content_md=fc.content_md, raw_html=fc.content_md, content_type=None)
    subsystem = None if regate.verdict is Verdict.ok else regate.subsystem
    fc.observe(
        kind=ObservationKind.gate_outcome,
        source="regate",
        verdict=regate.verdict,
        # Carry the escalation signal so a still-blocked escalation result can
        # re-trigger the playbook — this is what lets the fast `browser` rung
        # escalate to `browser_robust` when its render is still thin/blocked
        # (the browser rule requires `escalation.next_tier == "browser"`).
        escalation=regate.escalation,
        subsystem=subsystem,
    )


async def _escalate_browser(fc: FetchContext, *, state: AppState, scroll: bool = False) -> None:
    """Dispatch a browser rung out-of-band; install its result on success.

    `scroll` (listing-completeness Slice 2b) asks the browser to scroll the page
    to stable before snapshotting — the free own-browser listing-completion path.

    Two-rung fast→robust ladder on the SAME out-of-band dispatch: the rung is
    selected from `fc.browser_dispatches` — the first dispatch is the fast
    Chromium rung (`browser`, `fc.browser_backend`), the second the robust CDP
    rung (`browser_robust`, `fc.browser_robust_backend`). The playbook's browser
    rule (cap `< 2`) re-fires only when the fast render came back thin/blocked
    (gate still wants browser), so the robust rung never runs after a good fast
    render. Resolves the rung's `Lazy[...]` at this single seam — the engine only
    enters when its rung actually fires. A missing backend (caller didn't
    provision) surfaces `ResourceUnavailable`; we pass `backend=None` and the
    real `BrowserTier` short-circuits to an unavailable verdict.
    """
    is_robust = fc.browser_dispatches >= 1
    rung = "browser_robust" if is_robust else "browser"
    engine = state.settings.browser_backend_robust if is_robust else state.settings.browser_backend
    backend: BrowserBackend | None
    try:
        backend = await (fc.browser_robust_backend() if is_robust else fc.browser_backend())
    except ResourceUnavailable:
        backend = None
    browser_tier = REGISTRY[rung]
    br_start_ms = await _emit_tier_started(step=rung, host=_host(fc.final_url), start_perf=fc.start_perf)
    browser_result = await browser_tier.fetch(fc.final_url, state=state, backend=backend, scroll=scroll)
    fc.browser_dispatches += 1
    br_dur_ms = await _emit_tier_ended(
        step=rung,
        engine=engine,
        verdict=browser_result.verdict,
        start_ms=br_start_ms,
        start_perf=fc.start_perf,
        extra={"status_code": browser_result.status_code},
    )
    fc.diagnostics.append(
        Diagnostic(
            t_ms=br_start_ms,
            step=rung,
            engine=engine,
            host=_host(fc.final_url),
            proxy=None,
            verdict=browser_result.verdict,
            dur_ms=br_dur_ms,
            extra={"status_code": browser_result.status_code},
        )
    )
    browser_pre = browser_result.pre_rendered
    if browser_result.verdict == Verdict.ok and browser_pre is not None:
        fc.content_md = browser_pre.content_md
        fc.title = browser_pre.title
        fc.byline = browser_pre.byline
        fc.headings = browser_pre.headings
        fc.body = browser_result.body
        fc.content_type = browser_result.content_type
        fc.final_url = browser_result.final_url
        fc.tier_used = rung
        fc.pre_rendered_payload = browser_pre
        fc.status_code = browser_result.status_code
        # When browser-rendered markdown is under-extracted (Trendyol pattern —
        # __NEXT_DATA__ exposed post-hydration, or a server-rendered listing
        # trafilatura guts), run the extraction-escalation ladder against the
        # rendered DOM before re-gating — the ladder covers raw, browser, and
        # archive results uniformly.
        rendered_html = browser_result.body.decode("utf-8", errors="replace") if browser_result.body else ""
        if rendered_html:
            await _run_extraction_escalation(fc, raw_html=rendered_html)
        _regate_after_escalation(fc)
    elif browser_result.operator_hint is not None:
        fc.operator_hints.append(browser_result.operator_hint)


# Paid tiers tried, in order, by `_escalate_paid`. Only names present in
# REGISTRY (i.e. keyed at boot) are actually dispatched; an un-keyed deployment
# has neither and the escalation is a single no-op that burns the paid budget so
# the planner falls through to the late never-silently-miss hint.
_PAID_TIER_ORDER = ("zyte", "firecrawl")


async def _escalate_paid(fc: FetchContext, *, state: AppState, scroll: bool = False) -> None:
    """Dispatch the paid last-resort tier out-of-band; install on success.

    Cost-incurring, so capped at one escalation per fetch: `fc.paid_dispatches`
    is bumped unconditionally at entry (even when no paid tier is registered) so
    the planner's `paid_last_resort` rule cannot re-fire and spin.

    `scroll` (listing-completeness Slice 2) asks a browser-rendering paid tier
    to scroll the page before snapshotting — passed through to `tier.fetch`;
    tiers that don't render (Firecrawl) ignore it via `**kwargs`.

    FAIL-LOUD contract (task 4.6): a paid tier returning `paid_auth_error`
    (bad key / exhausted billing) records an AUTHORITATIVE observation and STOPS
    immediately — no fall-through to a sibling paid tier, no silent downgrade.
    The authoritative `paid_auth_error` (rank 12) then wins `resolve_verdict`, so
    the operator sees the real misconfiguration instead of a masked lower-tier
    result. A transient non-auth failure (timeout / connection) is recorded
    non-authoritatively and lets the next registered paid tier try.
    """
    fc.paid_dispatches += 1
    for tier_name in _PAID_TIER_ORDER:
        tier = REGISTRY.get(tier_name)
        if tier is None:
            continue  # un-keyed at boot — not registered.
        paid_start_ms = await _emit_tier_started(step=tier_name, host=_host(fc.final_url), start_perf=fc.start_perf)
        result = await tier.fetch(fc.final_url, state=state, scroll=scroll)
        paid_dur_ms = await _emit_tier_ended(
            step=tier_name,
            engine=tier_name,
            verdict=result.verdict,
            start_ms=paid_start_ms,
            start_perf=fc.start_perf,
            extra={"status_code": result.status_code},
        )
        fc.diagnostics.append(
            Diagnostic(
                t_ms=paid_start_ms,
                step=tier_name,
                engine=tier_name,
                host=_host(fc.final_url),
                proxy=None,
                verdict=result.verdict,
                dur_ms=paid_dur_ms,
                extra={"status_code": result.status_code},
            )
        )

        if result.verdict is Verdict.paid_auth_error:
            # Fail loud: authoritative hard-stop. Do NOT try the next paid tier.
            fc.observe(
                kind=ObservationKind.tier_outcome,
                source=tier_name,
                verdict=Verdict.paid_auth_error,
                authoritative=True,
                status_code=result.status_code,
            )
            return

        pre = result.pre_rendered
        if result.verdict is Verdict.ok and pre is not None:
            fc.content_md = pre.content_md
            fc.title = pre.title
            fc.byline = pre.byline
            fc.headings = pre.headings
            fc.body = result.body
            fc.content_type = result.content_type
            fc.final_url = result.final_url
            fc.tier_used = tier_name
            fc.pre_rendered_payload = pre
            fc.status_code = result.status_code
            fc.observe(kind=ObservationKind.tier_outcome, source=tier_name, verdict=Verdict.ok)
            # An HTML-returning paid tier (Zyte `browserHtml`) hands back a full
            # rendered page — a straight markdown conversion carries SPA nav +
            # inline-script noise. Run the extraction-escalation ladder
            # (trafilatura + json/record synth) on the HTML first, mirroring
            # `_escalate_browser`. Markdown-native paid tiers (Firecrawl) return
            # no HTML body, so this is skipped and the clean markdown stands.
            rendered_html = result.body.decode("utf-8", errors="replace") if ("html" in result.content_type and result.body) else ""
            if rendered_html:
                await _run_extraction_escalation(fc, raw_html=rendered_html)
            _regate_after_escalation(fc)
            return

        # Non-auth failure — record and let the next registered paid tier try.
        fc.observe(
            kind=ObservationKind.tier_outcome,
            source=tier_name,
            verdict=result.verdict,
            status_code=result.status_code,
        )


async def _phase_cache_write(fc: FetchContext, *, state: AppState) -> None:
    """Write to cache iff gate passed, non-hit, non-bypass, non-archive."""
    is_archive_result = fc.tier_used == "archive"
    should_cache = (
        fc.sqlite is not None
        and not fc.bypass_cache
        and fc.cache_state != CacheState.hit
        and fc.resolved_verdict() is Verdict.ok
        and fc.body
        and not is_archive_result
    )
    if not should_cache:
        return
    assert fc.sqlite is not None  # noqa: S101 — narrowed by should_cache

    cache_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.log.info(StageStarted(t_ms=cache_dur_start, step="cache_write"))
    await fc.sqlite.put(
        fc.url,
        fc.profile_hash,
        etag=fc.etag,
        last_modified=fc.last_modified,
        status_code=fc.status_code,
        content_type=fc.content_type,
        body=fc.body,
        ttl_s=_ttl_for(fc.content_type, state.settings),
    )
    cache_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - cache_dur_start
    await a2kit.log.info(
        StageEnded(t_ms=cache_dur_start, step="cache_write", verdict=Verdict.ok, dur_ms=cache_dur_ms),
    )


# --------------------------------------------------------------------- #
# Top-level coordinator + response builder
# --------------------------------------------------------------------- #


async def _run_pipeline(
    fc: FetchContext,
    *,
    state: AppState,
) -> FetchResponse:
    """Run the cascade end-to-end; return the response built from the context."""
    await _phase_cache_check(fc)
    await _phase_tier_loop(fc, state=state)
    # Cache hits still go through extract+gate — the body came from cache, but
    # the agent-facing fields (title, content_md, etc.) are produced by extraction.
    await _phase_extract(fc)
    await _phase_gate_and_escalate(fc, state=state)
    # v0.4: optional LLM extraction. Runs only when ask= is set and the fetch
    # succeeded. Graceful when no API key + no Claude Code OAuth available.
    await _phase_extract_answer(fc, state=state)
    # Obstacle-driven render: when the extractor flagged an empty/blocked
    # obstacle (a fat SPA shell that passed the gate), attempt one paid render +
    # re-extraction before declaring the retrieval incomplete. Runs BEFORE
    # cache_write so the final (possibly re-rendered) body is cached once and a
    # confabulated shell never lands in the cache.
    await _phase_obstacle_render(fc, state=state)
    # Listing scroll-to-complete: when a partial listing was flagged and
    # `complete_listings` is enabled, dispatch one bounded scrolling render to
    # load the rest of the items (shares the obstacle/wall paid-dispatch cap).
    # Runs BEFORE cache_write so the completed body is the one cached.
    await _phase_listing_render(fc, state=state)
    await _phase_cache_write(fc, state=state)
    # v0.8: emit cookies_stale hint once per fetch when mirror is stale.
    await _phase_cookies_staleness(fc, state=state)
    return build_response(fc)


async def _phase_extract_answer(
    fc: FetchContext,
    *,
    state: AppState,
) -> None:
    """Run server-side LLM extraction when ask= is set. v0.4.

    Resolves `Lazy[LlmExtractorResource]` at this seam — the LLM resource
    only enters when an `ask=` was passed AND the fetch succeeded.
    """
    if fc.ask is None:
        return
    if fc.resolved_verdict() is not Verdict.ok or not fc.content_md:
        # Failed fetches don't get extraction — no content to extract from.
        # The agent will see status=failed + diagnostics_summary explaining why.
        return
    phase_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.log.info(StageStarted(t_ms=phase_start_ms, step="extract_answer"))

    # v0.7 link-discovery: request next-links from the LLM in the same call.
    # Skip the extension when the off-switch is engaged.
    request_next_links = fc.next_links_enabled
    handler_candidates_for_llm = (
        [_to_llm_next_link(nl) for nl in fc.next_links_handler] if request_next_links and fc.next_links_handler else None
    )

    # Feed Haiku the full menu (prose + json_synth + record_synth), not the
    # single quality-picked `content_md` (ADR-0005). The menu is assembled
    # deterministically so the prompt-cache prefix stays byte-stable across
    # asks. Handler/pre-rendered pages skip the escalation ladder, leaving
    # `content_candidates` empty — fall back to `content_md` there.
    menu = assemble_menu(fc.content_candidates) or fc.content_md

    # One unavailability path: resolving the resource (not provisioned) and
    # awaiting the injected provider inside extract() (no provider configured)
    # both raise ResourceUnavailable. Graceful degrade — the fetch succeeded,
    # the operator hint surfaces the actionable reason.
    try:
        extractor_resource = await fc.llm_extractor()
        result = await extractor_resource.extract(
            content=menu,
            ask=fc.ask,
            request_next_links=request_next_links,
            handler_candidates=handler_candidates_for_llm,
            max_content_chars=fc.max_content_chars,
            request_routing=fc.include_routing,
        )
    except ResourceUnavailable as exc:
        fc.operator_hints.append(
            OperatorHint(
                code="llm_unavailable",
                message=exc.reason,
                fix=(
                    f"Set {state.settings.llm_api_key_env} (Anthropic) or OPENAI_API_KEY "
                    "(+ OPENAI_BASE_URL / OPENAI_MODEL) in the environment, or run inside "
                    "Claude Code. `fetch_raw` works without an LLM."
                ),
                severity="critical",
            )
        )
        dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
        await a2kit.log.info(
            StageEnded(
                t_ms=phase_start_ms,
                step="extract_answer",
                verdict=Verdict.other,
                dur_ms=dur_ms,
                extra={"skipped": "llm_unavailable"},
            ),
        )
        return
    fc.extracted_answer = result.answer

    # v0.7 link-discovery: validate LLM-supplied URLs against the markdown
    # the LLM was given. URLs not present in the content are dropped with a
    # drift diagnostic — defense against hallucinated URLs. Handler-supplied
    # URLs (re-rank flow) are exempt: they were in the prompt context, not
    # the markdown, but came from a trusted upstream source.
    if request_next_links and result.next_links:
        validated, dropped = _validate_llm_next_links_against_markdown(
            result.next_links,
            markdown=fc.content_md,
            handler_urls={nl.url for nl in fc.next_links_handler},
        )
        fc.next_links_llm = validated
        for drift_url in dropped:
            fc.diagnostics.append(
                Diagnostic(
                    t_ms=int((time.perf_counter() - fc.start_perf) * 1000),
                    step="extract_answer.next_links",
                    verdict=Verdict.other,
                    dur_ms=0,
                    extra={"event": "extraction_drift", "url": drift_url},
                ),
            )

    fc.extraction_meta = ExtractionMeta(
        model=result.model,
        template_name=result.template_name,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        cache_hit=result.cache_hit,
        truncated=bool(result.raw and result.raw.get("truncated")),
    )
    # v0.21 — surface the router-shape payload for the seam projector. When
    # the model returned malformed JSON or `include_routing=False`, this is
    # None.
    fc.routing = result.routing
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
    await a2kit.log.info(
        StageEnded(
            t_ms=phase_start_ms,
            step="extract_answer",
            verdict=Verdict.ok,
            dur_ms=dur_ms,
            extra={
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
        ),
    )


# Tiers that already execute JavaScript, so re-rendering their output via the
# paid tier would return the same content — the obstacle render is redundant.
_JS_EXECUTED_TIERS = frozenset({"jina", "browser", "browser_robust"})

# Above this much extracted content, the page is treated as complete (SSR /
# static): the answer's absence is real and a render can't add it. Only a THIN
# result (in the (LENGTH_FLOOR, ceiling) window) is plausibly an unrendered
# shell worth a render. This is the load-bearing guard for SSR framework sites
# (Next/Nuxt), which carry SPA mount markers yet already contain their content —
# markers alone can't tell an SSR page from a CSR shell.
_RENDER_CONTENT_CEILING = 2000


def _obstacle_wants_render(fc: FetchContext) -> bool:
    """True when the extractor's obstacle should drive one paid render.

    Gated hard on cost:
    - the ask path (obstacle exists only there);
    - an `empty`/`blocked` obstacle (`_INCOMPLETE_OBSTACLES` — shared with the
      retrieval-completeness logic so the trigger stays in lockstep;
      `paywalled`/`error` are excluded — a render won't clear a paywall);
    - an unspent paid budget (`paid_dispatches < 1`, so a prior gate/handler
      render suppresses this);
    - **evidence a render would actually add content** (the false-positive
      guard): the content did NOT come from a JS-executing tier (jina/browser
      already ran JS, so a render is redundant); the extracted content is THIN
      (`< _RENDER_CONTENT_CEILING`, so plausibly an unrendered shell rather than
      a complete SSR/static page that merely lacks the answer — the load-bearing
      check for Next/Nuxt SSR sites, which carry SPA markers yet already contain
      their content); AND the raw body shows unrendered-SPA markers. A complete
      page (a spec doc, a book, any content-rich SSR page) is NOT re-rendered.
    """
    if fc.ask is None or fc.routing is None:
        return False
    if fc.paid_dispatches >= 1:
        return False
    if fc.routing.obstacle not in _INCOMPLETE_OBSTACLES:
        return False
    if fc.tier_used in _JS_EXECUTED_TIERS:
        return False
    if len(fc.content_md) >= _RENDER_CONTENT_CEILING:
        return False
    raw = fc.body.decode("utf-8", errors="replace") if fc.body else ""
    return looks_like_unrendered_spa(raw)


async def _phase_obstacle_render(fc: FetchContext, *, state: AppState) -> None:
    """Attempt one paid render when the extractor flagged an unretrieved obstacle.

    The extractor is the only component that can say "the answer isn't in this
    content" (a fat SPA shell that passed the gate). When it reports
    `obstacle ∈ {empty, blocked}`, dispatch one paid render of the original URL —
    `_escalate_paid` already installs the rendered `content_md`, runs the
    extraction-escalation ladder, and re-gates — then re-run answer extraction
    over the real content. If the render produced nothing new (no paid tier keyed,
    failure, or an identical body), the v0.29.0 `retrieval_incomplete` signal
    stands (never-silently-miss). Bounded to one render + one extra LLM call.
    """
    if not _obstacle_wants_render(fc):
        return
    prev_md = fc.content_md
    await _escalate_paid(fc, state=state)
    if fc.content_md == prev_md:
        # No new content (unavailable / failed / paid_auth_error hard-stop /
        # identical shell) — leave the obstacle-flagged answer; the surviving
        # obstacle drives retrieval_incomplete in build_ask_response.
        return
    # Fresh content installed by the render — re-extract the answer over it. The
    # fresh obstacle is now authoritative for completeness.
    await _phase_extract_answer(fc, state=state)


def _listing_wants_render(fc: FetchContext, *, settings: AppSettings) -> bool:
    """True when a partial listing should drive one bounded scrolling render.

    Gated on cost + product surface (listing-completeness Slice 2):
    - `complete_listings` is enabled (the operator opted into paid egress on
      the common listing path);
    - the ask path is active (scroll-to-complete is the distilled-answer
      product; `fetch_raw` is signal-only);
    - the listing was flagged partial (`items_total` set by
      `_phase_listing_completeness`);
    - the shared paid budget is unspent (`paid_dispatches < 1` — one render per
      fetch, shared with the gate-wall and obstacle triggers);
    - the content did NOT come from a JS-executing tier (jina/browser already
      ran JS, so a scroll render is redundant);
    - the oracle is within the completeness ceiling (`listing_scroll_max`) —
      above it (a broad search with thousands of hits) the response steers
      toward a narrower query rather than scrolling the universe.
    """
    if not settings.complete_listings:
        return False
    if fc.ask is None:
        return False
    if fc.items_total is None:
        return False
    if fc.paid_dispatches >= 1:
        return False
    if fc.tier_used in _JS_EXECUTED_TIERS:
        return False
    return fc.items_total <= settings.listing_scroll_max


async def _phase_listing_render(fc: FetchContext, *, state: AppState) -> None:
    """Complete a partial listing with one bounded scrolling render (Slice 2 / 2b).

    Free own-browser first, paid egress second (spec: own-browser preferred).
    When `browser_enabled`, a free browser render scrolls the original URL to
    stable; only if that changed nothing (browser off / unavailable / failed) and
    the single paid budget remains does the paid Zyte scroll fire. Either render
    re-counts the records the fuller page yields (via the shared extraction
    escalation) and the listing is re-assessed: complete → the `listing_partial`
    signal is dropped (fields nulled); still short (a capped or DOM-virtualised
    scroll) → the signal stands with the updated count, the miss loud. If nothing
    rendered, the Slice 1 signal stands unchanged.
    """
    if not _listing_wants_render(fc, settings=state.settings):
        return
    prev_md = fc.content_md
    # Free own-browser scroll first — no egress cost, just latency.
    if state.settings.browser_enabled:
        await _escalate_browser(fc, state=state, scroll=True)
    # Paid fallback only if the free attempt changed nothing and budget remains.
    if fc.content_md == prev_md and fc.paid_dispatches < 1:
        await _escalate_paid(fc, state=state, scroll=True)
    if fc.content_md == prev_md:
        return  # nothing rendered → the partial signal stands (never-silently-miss).
    if fc.record_count is None or fc.items_total is None:
        return
    if content_expectations.assess(loaded=fc.record_count, total=fc.items_total) == "partial":
        fc.items_loaded = fc.record_count  # still short — keep the signal, updated count.
    else:
        fc.items_loaded = None  # completed — clear the signal.
        fc.items_total = None
    if fc.ask is not None:
        await _phase_extract_answer(fc, state=state)


def _to_llm_next_link(nl: NextLink) -> LlmNextLink:
    """Convert a domain `NextLink` into the package boundary `LlmNextLink` shape."""
    return LlmNextLink(anchor=nl.anchor, url=nl.url, reason=nl.reason, kind=nl.kind)


def _validate_llm_next_links_against_markdown(
    llm_next_links: list[LlmNextLink],
    *,
    markdown: str,
    handler_urls: set[str],
) -> tuple[list[NextLink], list[str]]:
    """Validate LLM-supplied URLs appear in the markdown OR were handler-supplied.

    Returns `(validated_NextLinks, dropped_urls)`. URLs that don't appear in
    the markdown AND weren't in `handler_urls` are dropped — defense against
    hallucinated URLs. Pydantic validation runs on the conversion; entries
    failing validation are silently skipped (provider misbehavior, not the
    user's problem).
    """
    validated: list[NextLink] = []
    dropped: list[str] = []
    for nl in llm_next_links:
        # Cheap substring check is enough — markdown links render as `(url)` so a
        # naive `url in markdown` covers `[anchor](url)` AND raw `<url>` forms.
        if nl.url not in markdown and nl.url not in handler_urls:
            dropped.append(nl.url)
            continue
        try:
            validated.append(
                NextLink(
                    anchor=nl.anchor,
                    url=nl.url,
                    reason=nl.reason,
                    kind=cast(NextLinkKind, nl.kind),
                ),
            )
        except Exception:  # pydantic ValidationError; silent drop on provider misbehavior
            dropped.append(nl.url)
    return validated, dropped


def _host(url: str) -> str | None:
    from urllib.parse import urlparse

    return urlparse(url).hostname
