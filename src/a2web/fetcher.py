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
import a2kit.ldd
import structlog
from a2kit import Lazy

from .actions import Action, EscalateBrowser, PlannerCaps, RetryViaArchive, RewriteUrl, decide_next
from .cookie_jar import Cookie, CookieJarResource
from .decision_log import Observation, ObservationKind, resolve_verdict
from .domain import (
    compute_profile_hash,
    is_live_only,
    json_to_markdown_rows,
    rewrite_captcha_host,
)
from .events import StageEnded, StageStarted, TierEnded, TierStarted
from .events.types import CookiesAttached, CookiesStale
from .fetcher_response import build_response
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
)
from .packages.block_detector import evaluate as _package_evaluate
from .packages.browser_pool import BrowserPool
from .packages.content_extract import (
    extract_markdown as _package_extract_markdown,
)
from .packages.content_extract import (
    parse_metadata,
)
from .packages.escalation import EscalationSignal
from .packages.http_cache import CacheRow, SqliteResource
from .packages.json_in_script import extract_json_payloads, rank_payloads
from .packages.llm_extract import LlmNextLink, RouterPayload
from .packages.record_extract import Record, RecordSet, extract_records
from .settings import AppSettings
from .state import AppState, ResourceUnavailable, unavailable_lazy
from .tiers import REGISTRY, TIER_ORDER, Rendered, Tier, TierResult


@_dc(slots=True)
class _GateResult:
    """Domain-typed wrapper over `packages.block_detector.BlockResult`."""

    verdict: Verdict
    subsystem: str | None = None
    escalation: EscalationSignal | None = None


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

    return _GateResult(verdict=verdict, subsystem=subsystem, escalation=escalation)


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


_LOG = structlog.get_logger("a2web")


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
    # actually need browser or LLM extraction `await fc.browser_pool()` /
    # `await fc.llm_extractor()` to resolve the resource once at the seam.
    # Resources never enter when their consuming phase doesn't fire.
    #
    # Non-optional (Phase 3 of fetcher-orchestrator-refactor-v1): the `fetch()`
    # entrypoint normalizes any `None` caller-kwarg to an `unavailable_lazy(...)`
    # stub before constructing FetchContext, so phases never check for `None` —
    # they `await` uniformly and catch `ResourceUnavailable` to emit the
    # graceful operator hint.
    browser_pool: Lazy[BrowserPool] = field(
        default_factory=lambda: unavailable_lazy(BrowserPool, reason="browser_pool not provisioned"),
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
    browser_pool: Lazy[BrowserPool] | None = None,
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

    Emits typed phase-boundary events via `await a2kit.ldd.event(EventInstance(...))`.
    The dispatcher binds the active ToolContext as ambient state (a2kit v0.29+);
    when called outside a tool dispatch (eval/systems direct call), wrap with
    `async with a2kit.testing.ldd_state_for_call(ctx=...):` if events are needed,
    otherwise `AmbientContextMissing` will surface immediately — fail-loud.

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
        browser_pool
        if browser_pool is not None
        else unavailable_lazy(
            BrowserPool,
            reason="browser_pool not provisioned by caller",
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
        browser_pool=browser_lazy,
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


# Note: typed events emit directly via `await a2kit.ldd.event(event)`.
# Round-4: a2kit's free function now honors registered dataclass instances and
# serializes them via `dataclasses.asdict` + Enum.value coercion. No flattener
# needed at this seam.


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
    await a2kit.ldd.event(TierStarted(t_ms=start_ms, step=step, host=host))
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
    await a2kit.ldd.event(
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
        await a2kit.ldd.event(
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
    """Append the `cookies_stale` operator hint and LDD event when stale.

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
    await a2kit.ldd.event(
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

            await a2kit.ldd.event(TierStarted(t_ms=tier_start_ms, step=tier_name, host=_host(fc.url)))

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

    if not (fc.body and fc.resolved_verdict() is Verdict.ok):
        return

    await a2kit.ldd.event(StageStarted(t_ms=extract_dur_start, step="extract"))
    extract_result = await extract_markdown(raw_html, fc.final_url)
    fc.content_md = extract_result.content_md
    fc.title = extract_result.title
    fc.byline = extract_result.byline
    fc.published = extract_result.published
    fc.headings = extract_result.headings
    fc.links = extract_result.links
    fc.meta_dict = parse_metadata(raw_html)
    await _run_extraction_escalation(fc, raw_html=raw_html)
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
    await a2kit.ldd.event(
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
    the full set reaches the extractor via the menu. Pure function — emits LDD
    telemetry, does NOT mutate `fc.content_md`.
    """
    t_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(StageStarted(t_ms=t_ms, step="json_synth"))
    payloads = extract_json_payloads(raw_html)
    candidates: list[ContentCandidate] = []
    seen: set[str] = set()
    for payload in rank_payloads(payloads):
        rendered = json_to_markdown_rows(payload)
        if rendered and rendered not in seen:
            seen.add(rendered)
            candidates.append(ContentCandidate(source="json_synth", content_md=rendered))
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - t_ms
    outcome = "no_payloads" if not payloads else ("no_synth" if not candidates else "collected")
    await a2kit.ldd.event(
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
    await a2kit.ldd.event(StageStarted(t_ms=t_ms, step="record_synth"))
    record_set = extract_records(raw_html, base_url=fc.final_url or "")
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - t_ms
    if record_set is not None:
        synthetic = record_set.to_markdown()
        if synthetic:
            next_links = _records_to_next_links(record_set, page_url=fc.final_url or "")
            await a2kit.ldd.event(
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
    await a2kit.ldd.event(StageEnded(t_ms=t_ms, step="record_synth", verdict=Verdict.ok, dur_ms=dur_ms, extra={"outcome": outcome}))
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
    if not (fc.body and fc.resolved_verdict() is Verdict.ok):
        return

    gate_dur_start = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(StageStarted(t_ms=gate_dur_start, step="gate"))

    # Pre-rendered handler results carry application/json bodies; skip the
    # html/content-type guard for them — block-page regexes still run on the
    # rendered markdown and length floor catches truly empty results.
    is_pre_rendered = fc.pre_rendered_payload is not None
    gate_content_type = None if is_pre_rendered else fc.content_type
    gate_raw_html = fc.content_md if is_pre_rendered else (fc.body.decode("utf-8", errors="replace") if fc.body else "")
    gate_result = evaluate(
        content_md=fc.content_md,
        raw_html=gate_raw_html,
        content_type=gate_content_type,
        tier=fc.tier_used,
        host=urlparse(fc.final_url).hostname if fc.final_url else None,
        settings=state.settings,
    )
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
    await a2kit.ldd.event(
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
        else:
            break  # Continue (or a URL rewrite — not used post-gate)


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
        subsystem=subsystem,
    )


async def _escalate_browser(fc: FetchContext, *, state: AppState) -> None:
    """Dispatch the browser tier out-of-band; install its result on success.

    Resolves the `Lazy[BrowserPool]` at this single seam — BrowserPool only
    enters when an escalation actually fires. When the caller didn't
    provision a real pool, the stub raises `ResourceUnavailable` and we pass
    `pool=None` to the tier: the real `BrowserTier` short-circuits to an
    unavailable verdict, and direct-call test stubs (REGISTRY["browser"])
    ignore the kwarg.
    """
    try:
        pool: BrowserPool | None = await fc.browser_pool()
    except ResourceUnavailable:
        pool = None
    browser_tier = REGISTRY["browser"]
    br_start_ms = await _emit_tier_started(step="browser", host=_host(fc.final_url), start_perf=fc.start_perf)
    browser_result = await browser_tier.fetch(fc.final_url, state=state, pool=pool)
    fc.browser_dispatches += 1
    br_dur_ms = await _emit_tier_ended(
        step="browser",
        engine="camoufox",
        verdict=browser_result.verdict,
        start_ms=br_start_ms,
        start_perf=fc.start_perf,
        extra={"status_code": browser_result.status_code},
    )
    fc.diagnostics.append(
        Diagnostic(
            t_ms=br_start_ms,
            step="browser",
            engine="camoufox",
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
        fc.tier_used = "browser"
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
    await a2kit.ldd.event(StageStarted(t_ms=cache_dur_start, step="cache_write"))
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
    await a2kit.ldd.event(
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
    await _phase_cache_write(fc, state=state)
    # v0.4: optional LLM extraction. Runs only when ask= is set and the fetch
    # succeeded. Graceful when no API key + no Claude Code OAuth available.
    await _phase_extract_answer(fc, state=state)
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
    await a2kit.ldd.event(StageStarted(t_ms=phase_start_ms, step="extract_answer"))

    try:
        extractor_resource = await fc.llm_extractor()
    except ResourceUnavailable as exc:
        fc.operator_hints.append(
            OperatorHint(
                code="llm_unavailable",
                message=f"LLM extractor not provisioned ({exc.reason})",
                fix="invoke via WebRouter.fetch or pass llm_extractor=Lazy[LlmExtractorResource]",
            )
        )
        return

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
    result = await extractor_resource.extract(
        content=menu,
        ask=fc.ask,
        request_next_links=request_next_links,
        handler_candidates=handler_candidates_for_llm,
        max_content_chars=fc.max_content_chars,
        request_routing=fc.include_routing,
    )
    if result is None:
        # Graceful degrade: fetch succeeded, extraction skipped, operator
        # hint surfaces the actionable reason.
        reason = extractor_resource.unavailable_reason or "LLM extractor unavailable"
        fc.operator_hints.append(
            OperatorHint(
                code="llm_unavailable",
                message=reason,
                fix=f"Set {state.settings.llm_api_key_env} in the environment or run inside Claude Code.",
            )
        )
        dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - phase_start_ms
        await a2kit.ldd.event(
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
    await a2kit.ldd.event(
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
