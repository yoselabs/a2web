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
from typing import cast
from urllib.parse import urlparse

import a2kit
import a2kit.ldd
import structlog
from a2kit.packages.di import Lazy

from .actions import RetryViaArchive, RewriteUrl, next_action_after_gate, next_action_after_tier
from .cookie_jar import Cookie, CookieJarResource
from .domain import (
    compute_profile_hash,
    count_sentences,
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
from .packages.http_cache import CacheRow, SqliteResource
from .packages.json_in_script import extract_json_payloads, rank_payloads
from .packages.llm_extract import LlmNextLink
from .settings import AppSettings
from .state import AppState
from .tiers import REGISTRY, TIER_ORDER, Rendered, Tier, TierResult


@_dc(slots=True)
class _GateResult:
    """Domain-typed wrapper over `packages.block_detector.BlockResult`."""

    verdict: Verdict
    subsystem: str | None = None
    suggested_tier: str | None = None


_JINA_PAYWALL_STUB_RE = re.compile(r"Target URL returned error 40[13]")
_JINA_STUB_MAX_BODY: int = 2_048
_THIN_BROWSER_MAX_BODY: int = 1_024

# Hosts known to be JS-heavy CSR apps. When the browser tier returns a thin
# 200 OK from one of these, the gate downgrades to length_floor so escalation
# continues (operator can extend via AppSettings.js_heavy_hosts_extra).
_JS_HEAVY_HOSTS_SEED: frozenset[str] = frozenset({
    "x.com", "twitter.com", "instagram.com", "tiktok.com",
    "trendyol.com", "aliexpress.com",
})


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
    suggested_tier = result.suggested_tier

    if tier == "jina" and len(content_md) < _JINA_STUB_MAX_BODY and _JINA_PAYWALL_STUB_RE.search(content_md):
        verdict = Verdict.paywall
        subsystem = "jina_stub"
        suggested_tier = None  # archive playbook handles next step

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

    return _GateResult(verdict=verdict, subsystem=subsystem, suggested_tier=suggested_tier)


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
    # Defaulted to None so legacy direct-call paths (eval / tests) still build a
    # FetchContext without DI wiring — phases emit a graceful operator hint when
    # they need a resource that wasn't provisioned.
    browser_pool: Lazy[BrowserPool] | None = None
    llm_extractor: Lazy[LlmExtractorResource] | None = None
    cookie_jar: Lazy[CookieJarResource] | None = None

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

    # Body & verdict state (set by tier loop, mutated by escalations)
    body: bytes = b""
    content_type: str = ""
    status_code: int = 0
    tier_used: str = "none"
    final_verdict: Verdict = Verdict.other
    etag: str | None = None
    last_modified: str | None = None
    pre_rendered_payload: Rendered | None = None
    # Set when a site handler returned `Verdict.not_found` — the site expert's
    # authoritative "content is gone" signal. `_phase_reconcile_verdict` restores
    # it over a vaguer downstream failure verdict when the fetch ultimately fails.
    handler_not_found: bool = False

    # Cache state
    cache_state: CacheState = CacheState.miss
    cached_row: CacheRow | None = None

    # Per-fetch escalation caps
    url_rewrites: int = 0
    archive_dispatches: int = 0
    browser_dispatches: int = 0

    # Extraction outputs
    content_md: str = ""
    title: str | None = None
    byline: str | None = None
    published: date | None = None
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    meta_dict: dict[str, str] = field(default_factory=dict)

    # Gate state
    gate_verdict: Verdict = Verdict.ok
    gate_subsystem: str | None = None

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

    fc = FetchContext(
        started_at=started_at,
        start_perf=start_perf,
        profile_hash=profile_hash,
        sqlite=sqlite,
        bypass_cache=bypass_cache,
        browser_pool=browser_pool,
        llm_extractor=llm_extractor,
        cookie_jar=cookie_jar,
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

    No-op when `cookie_source == "none"` or no cookie_jar Lazy was provided
    (legacy direct call paths). Re-resolves when `fc.url`'s host has changed
    since the last call (e.g. after `RewriteUrl`). Emits a redacted
    `CookiesAttached` event on a non-empty resolution.
    """
    if state.settings.cookie_source == "none":
        return
    if fc.cookie_jar is None:
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

    jar = await fc.cookie_jar()
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
    if fc.cookie_jar is None:
        return
    if fc.cookies_stale_hint_appended:
        return
    jar = await fc.cookie_jar()
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


class _AfterTier(Enum):
    """Outcome of `_apply_after_tier_action` — drives outer-loop control flow."""

    NONE = "none"  # no rewrite / archive — continue normal tier-loop flow
    REWRITE = "rewrite"  # URL was rewritten — restart the loop
    ARCHIVE_INSTALLED = "archive_installed"  # archive content installed onto fc


def _install_won_tier(
    fc: FetchContext,
    tier_result: TierResult,
    tier_name: str,
    tier: Tier,
) -> None:
    """Install a winning (`Verdict.ok`) tier result onto FetchContext."""
    fc.body = tier_result.body
    fc.content_type = tier_result.content_type
    fc.status_code = tier_result.status_code
    fc.final_url = tier_result.final_url
    fc.tier_used = tier_result.handler_name or (tier.name if hasattr(tier, "name") else tier_name)
    fc.final_verdict = Verdict.ok
    fc.etag = tier_result.headers.get("etag")
    fc.last_modified = tier_result.headers.get("last-modified")
    fc.pre_rendered_payload = tier_result.pre_rendered
    # v0.7 link-discovery: thread Tier-1 candidates from the handler into fc.
    fc.next_links_handler = list(tier_result.next_links)


def _install_archive_payload(fc: FetchContext, outcome: _ArchiveOutcome) -> None:
    """Install a successful archive escalation outcome onto FetchContext."""
    fc.body = outcome.body
    fc.content_type = outcome.content_type
    fc.final_url = outcome.final_url
    fc.tier_used = "archive"
    fc.pre_rendered_payload = outcome.pre_rendered
    fc.status_code = outcome.status_code
    fc.final_verdict = Verdict.ok


async def _apply_after_tier_action(
    fc: FetchContext,
    tier_result: TierResult,
    *,
    state: AppState,
) -> _AfterTier:
    """Run the after-tier action (URL rewrite, archive retry) and report outcome.

    Caps: `RewriteUrl` and `RetryViaArchive` each fire at most once per
    fetch. On `REWRITE`, the new URL is installed on `fc` and the
    cached row is reloaded. On `ARCHIVE_INSTALLED`, the archive payload
    is installed on `fc` (caller can return from the tier loop).
    """
    tier_action = next_action_after_tier(tier_result, fc.url)

    if isinstance(tier_action, RewriteUrl) and fc.url_rewrites < 1:
        fc.url_rewrites += 1
        fc.url = tier_action.new_url
        fc.final_url = fc.url
        # Reset cached_row — new URL likely has its own cache entry.
        if fc.sqlite is not None:
            fc.cached_row = await fc.sqlite.get(fc.url, fc.profile_hash)
        else:
            fc.cached_row = None
        return _AfterTier.REWRITE

    if isinstance(tier_action, RetryViaArchive) and fc.archive_dispatches < 1:
        fc.archive_dispatches += 1
        outcome = await _dispatch_archive(
            tier_action.url,
            state=state,
            start_perf=fc.start_perf,
            diagnostics=fc.diagnostics,
        )
        if outcome.success:
            _install_archive_payload(fc, outcome)
            return _AfterTier.ARCHIVE_INSTALLED
        # Archive failed — keep trying tiers (fall through).

    return _AfterTier.NONE


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
                fc.final_verdict = Verdict.proxy_unavailable
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

            # A site handler's `not_found` is the strongest negative signal in
            # the pipeline — remember it so a downstream generic tier can't bury
            # it under a vaguer verdict (`_phase_reconcile_verdict`).
            if tier_name == "site_handler" and tier_result.verdict == Verdict.not_found:
                fc.handler_not_found = True

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
                fc.final_verdict = Verdict.ok
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

            after = await _apply_after_tier_action(fc, tier_result, state=state)
            if after is _AfterTier.REWRITE:
                restart_loop = True
                break  # break inner for; while True restarts
            if after is _AfterTier.ARCHIVE_INSTALLED:
                return

            if tier_result.verdict == Verdict.ok:
                _install_won_tier(fc, tier_result, tier_name, tier)
                return

            fc.final_verdict = tier_result.verdict

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

    if not (fc.body and fc.final_verdict == Verdict.ok):
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
    await _maybe_synthesize_from_json(fc, raw_html=raw_html, extract_dur_start=extract_dur_start)
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


_JSON_SYNTH_THIN_CHARS: int = 2_048
_JSON_SYNTH_THIN_SENTENCES: int = 3
_JSON_SYNTH_REPLACE_RATIO: float = 2.0


async def _maybe_synthesize_from_json(fc: FetchContext, *, raw_html: str, extract_dur_start: int) -> None:
    """Run the JSON-in-script path when trafilatura returns thin output.

    Replaces `fc.content_md` with synthetic markdown ONLY IF a ranked payload
    produces >=2x the original length. Emits a `json_synth` LDD event with
    verdict in {"replaced","kept_original","no_payloads","no_synth"}.
    """
    original_len = len(fc.content_md or "")
    if original_len >= _JSON_SYNTH_THIN_CHARS and count_sentences(fc.content_md or "") >= _JSON_SYNTH_THIN_SENTENCES:
        return  # not thin — skip
    t_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(StageStarted(t_ms=t_ms, step="json_synth"))
    payloads = extract_json_payloads(raw_html)
    if not payloads:
        await a2kit.ldd.event(
            StageEnded(t_ms=t_ms, step="json_synth", verdict=Verdict.ok, dur_ms=0, extra={"outcome": "no_payloads"})
        )
        return
    ranked = rank_payloads(payloads)
    synthetic = ""
    for payload in ranked:
        candidate = json_to_markdown_rows(payload)
        if candidate:
            synthetic = candidate
            break
    if not synthetic:
        await a2kit.ldd.event(
            StageEnded(t_ms=t_ms, step="json_synth", verdict=Verdict.ok, dur_ms=0, extra={"outcome": "no_synth"})
        )
        return
    if len(synthetic) >= max(int(original_len * _JSON_SYNTH_REPLACE_RATIO), 128):
        fc.content_md = synthetic
        outcome = "replaced"
    else:
        outcome = "kept_original"
    dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - t_ms
    await a2kit.ldd.event(
        StageEnded(
            t_ms=t_ms,
            step="json_synth",
            verdict=Verdict.ok,
            dur_ms=dur_ms,
            extra={"outcome": outcome, "original_chars": original_len, "synth_chars": len(synthetic)},
        )
    )


async def _phase_gate_and_escalate(fc: FetchContext, *, state: AppState) -> None:
    """Run the gate; on signals, escalate to browser or archive (each capped to 1)."""
    if not (fc.body and fc.final_verdict == Verdict.ok):
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
    fc.gate_verdict = gate_result.verdict
    fc.gate_subsystem = gate_result.subsystem
    gate_dur_ms = int((time.perf_counter() - fc.start_perf) * 1000) - gate_dur_start
    fc.diagnostics.append(
        Diagnostic(
            t_ms=gate_dur_start,
            step="gate",
            engine="block_detector",
            host=None,
            proxy=None,
            verdict=fc.gate_verdict,
            subsystem=fc.gate_subsystem,
            dur_ms=gate_dur_ms,
            extra={},
        )
    )
    await a2kit.ldd.event(
        StageEnded(t_ms=gate_dur_start, step="gate", verdict=fc.gate_verdict, dur_ms=gate_dur_ms),
    )
    if fc.gate_verdict != Verdict.ok:
        fc.final_verdict = fc.gate_verdict

    # v0.7: search-engine captcha escape — block detector flagged a Google/Bing
    # captcha page that slipped past `rewrite_captcha_host`. Surface an
    # actionable operator hint instead of just an opaque `block_page_detected`.
    if fc.gate_subsystem == "captcha_redirect":
        fc.operator_hints.append(
            OperatorHint(
                code="captcha_redirect",
                message="Search engine returned a captcha page; consider DDG/Brave directly.",
                fix="https://duckduckgo.com/html/?q=<your-query>",
            )
        )

    # Browser escalation — cap=1, only if gate flagged browser
    if gate_result.suggested_tier == "browser" and fc.browser_dispatches < 1 and fc.gate_verdict != Verdict.ok:
        await _escalate_browser(fc, state=state)

    # Archive escalation — cap=1 (shared with after-tier archive_dispatches)
    gate_action = next_action_after_gate(fc.gate_verdict, fc.final_url)
    if isinstance(gate_action, RetryViaArchive) and fc.archive_dispatches < 1:
        fc.archive_dispatches += 1
        outcome = await _dispatch_archive(
            gate_action.url,
            state=state,
            start_perf=fc.start_perf,
            diagnostics=fc.diagnostics,
        )
        if outcome.success and outcome.pre_rendered is not None:
            fc.content_md = outcome.pre_rendered.content_md
            fc.title = outcome.pre_rendered.title
            fc.byline = outcome.pre_rendered.byline
            fc.headings = outcome.pre_rendered.headings
            fc.body = outcome.body
            fc.content_type = outcome.content_type
            fc.final_url = outcome.final_url
            fc.tier_used = "archive"
            fc.pre_rendered_payload = outcome.pre_rendered
            _regate_after_escalation(fc)


def _regate_after_escalation(fc: FetchContext) -> None:
    """Re-evaluate the gate on freshly-installed escalation content.

    Used after both browser and gate-path archive installs. Mutates
    `fc.gate_verdict` / `fc.final_verdict` / `fc.gate_subsystem`. The
    pre-rendered markdown plays both the `content_md` and `raw_html`
    roles — the underlying body is no longer the discriminator at this
    point in the pipeline.
    """
    regate = evaluate(content_md=fc.content_md, raw_html=fc.content_md, content_type=None)
    if regate.verdict == Verdict.ok:
        fc.final_verdict = Verdict.ok
        fc.gate_verdict = Verdict.ok
        fc.gate_subsystem = None
    else:
        fc.final_verdict = regate.verdict
        fc.gate_verdict = regate.verdict
        fc.gate_subsystem = regate.subsystem


async def _escalate_browser(fc: FetchContext, *, state: AppState) -> None:
    """Dispatch the browser tier out-of-band; install its result on success.

    Resolves the `Lazy[BrowserPool]` at this single seam — BrowserPool only
    enters when an escalation actually fires. Direct-call test paths that
    inject a stub `REGISTRY['browser']` may pass `pool=None`; the stub tier
    swallows the kwarg via `**kwargs` and returns its hardcoded result.
    The real `BrowserTier` short-circuits to an unavailable verdict when
    `pool is None`.
    """
    pool = await fc.browser_pool() if fc.browser_pool is not None else None
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
        # v0.11: when browser-rendered markdown is thin (Trendyol pattern —
        # __NEXT_DATA__ exposed post-hydration but trafilatura still gets nav
        # chrome), try the JSON-in-script path against the rendered DOM
        # before re-gating. Replaces fc.content_md when synth >= 2x original.
        rendered_html = browser_result.body.decode("utf-8", errors="replace") if browser_result.body else ""
        if rendered_html:
            await _maybe_synthesize_from_json(fc, raw_html=rendered_html, extract_dur_start=br_start_ms)
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
        and fc.final_verdict == Verdict.ok
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


def _phase_reconcile_verdict(fc: FetchContext) -> None:
    """Restore a site handler's `not_found` over a vaguer downstream failure verdict.

    A site handler returning `Verdict.not_found` confirmed the content is gone.
    When the fetch ultimately fails, that authoritative verdict outranks any
    vaguer verdict (`length_floor`, `other`) a downstream generic tier left on
    `final_verdict`. A genuine recovery (`final_verdict == ok`) is left
    untouched — the precedence rule never degrades a real result.
    """
    if fc.final_verdict != Verdict.ok and fc.handler_not_found:
        fc.final_verdict = Verdict.not_found


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
    _phase_reconcile_verdict(fc)
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
    if fc.final_verdict != Verdict.ok or not fc.content_md:
        # Failed fetches don't get extraction — no content to extract from.
        # The agent will see status=failed + diagnostics_summary explaining why.
        return
    if fc.llm_extractor is None:
        fc.operator_hints.append(
            OperatorHint(
                code="llm_unavailable",
                message="LLM extractor was not provisioned for this fetch call",
                fix="invoke via WebRouter.fetch or pass llm_extractor=Lazy[LlmExtractorResource]",
            )
        )
        return

    phase_start_ms = int((time.perf_counter() - fc.start_perf) * 1000)
    await a2kit.ldd.event(StageStarted(t_ms=phase_start_ms, step="extract_answer"))

    extractor_resource = await fc.llm_extractor()

    # v0.7 link-discovery: request next-links from the LLM in the same call.
    # Skip the extension when the off-switch is engaged.
    request_next_links = fc.next_links_enabled
    handler_candidates_for_llm = (
        [_to_llm_next_link(nl) for nl in fc.next_links_handler] if request_next_links and fc.next_links_handler else None
    )

    result = await extractor_resource.extract(
        content=fc.content_md,
        ask=fc.ask,
        request_next_links=request_next_links,
        handler_candidates=handler_candidates_for_llm,
        max_content_chars=fc.max_content_chars,
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
