"""__init__."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal, cast
from urllib.parse import urljoin, urlparse

import aiosqlite
from any_browser import BrowserBackend
from async_scope import Lazy
from content_extract import parse_metadata
from json_in_html import (
    JsonPayload,
    extract_json_payloads,
    is_answer_bearing,
    is_json_content_type,
    parse_json_response,
    rank_payloads,
)
from record_mine import Record, RecordSet, extract_records

from .. import content_expectations
from ..actions import (
    PAID_DISPATCH_CAP,
    Action,
    EscalateBrowser,
    EscalatePaid,
    PlannerCaps,
    RetryViaArchive,
    RewriteUrl,
    decide_next,
)
from ..actions.empty import is_complete_small_page, is_confirmed_empty
from ..actions.terminal import TerminalOutcome, classify_terminal
from ..cache import CacheRow, SqliteResource
from ..cookie_jar import Cookie, CookieJarResource
from ..decision_log import Observation, ObservationKind, resolve_verdict
from ..domain import (
    compute_profile_hash,
    is_live_only,
    rewrite_captcha_host,
    strip_reader_prefix,
)
from ..events import StageEnded, StageStarted, TierEnded, TierStarted
from ..events.types import CookiesAttached, CookiesStale, CorrelatedWitnessRung
from ..fetcher_response import _INCOMPLETE_OBSTACLES, build_response
from ..hints import (
    OperatorHint,
    captcha_redirect_hint,
    content_empty_hint,
    content_not_found_hint,
    content_thin_hint,
    cookies_stale_hint,
    fetch_deadline_hint,
    has_hint,
    llm_unavailable_hint,
    paid_auth_error_hint,
    try_user_browser_hint,
)
from ..link_digest import LinkDigest, build_digest
from ..listing_oracle import listing_has_more, listing_oracle
from ..llm_resource import LlmExtractorResource
from ..log import log_warning
from ..models import CacheState, Diagnostic, ExtractionMeta, FetchResponse, Heading, Link, NextLink, NextLinkKind, Verdict
from ..packages.block_detector import LENGTH_FLOOR, THIN_FALLTHROUGH, looks_like_unrendered_spa
from ..packages.escalation import EscalationSignal
from ..packages.llm_extract import LlmNextLink, OtherPageBoundary, RouterPayload, RoutingOutcome
from ..packages.structured_render import json_response_fallback, json_to_markdown_rows, listing_rows
from ..settings import AppSettings
from ..state import AppState, ResourceUnavailable, unavailable_lazy
from ..tiers import REGISTRY, TIER_ORDER, Rendered, Tier, TierResult
from ..uptake import note_visit, record_suggestions

# The tree is an implementation detail of : every name the
# package used to expose is re-exported here, so ~19 test modules and every
# internal caller keep the import they had.  below is what stops
# these reading as unused. A LATER change may narrow this surface; doing it
# in the same commit as the move would hide a rename inside a 3000-line diff.
from .answer.digest import _DIGEST_GATE_SOURCES, _DIGEST_LINK_CAP, _build_link_digest, _rehydrate_routing_handles
from .answer.links import (
    _ARCHIVE_MIRROR_HOSTS,
    _COMMENT_COUNT_RE,
    _heading_link_kind,
    _is_archive_mirror,
    _record_discussion_link,
    _records_to_next_links,
    _to_llm_next_link,
    _validate_llm_next_links_against_markdown,
)
from .answer.obstacle import (
    _JS_EXECUTED_TIERS,
    _RENDER_CONTENT_CEILING,
    _listing_wants_render,
    _obstacle_wants_render,
    _phase_listing_render,
    _phase_obstacle_render,
)
from .answer.prompt_call import _phase_answer, _phase_extract_answer
from .comprehension.extract import _ExtractResult, _phase_extract, extract_markdown
from .comprehension.gate import (
    _JS_HEAVY_HOSTS_SEED,
    _THIN_BROWSER_MAX_BODY,
    _GateResult,
    _regate_after_escalation,
    evaluate,
    js_heavy_hosts,
)
from .comprehension.ladder import (
    _PROSE_METADATA_LD_TYPES,
    _escalate_via_json,
    _escalate_via_records,
    _is_prose_metadata_ld,
    _rows_to_record_set,
    _run_extraction_escalation,
)
from .comprehension.menu import _MENU_LABELS, _normalize_ws, _pick_display_candidate, _suppress_subsets, _wire_content_md, assemble_menu
from .context import (
    ContentCandidate,
    DeadlineExceeded,
    FetchContext,
    GateOutcomeProjection,
    _check_deadline,
    _remaining_budget,
    _within_budget,
)
from .pipeline import _record_deadline, _record_uptake, _run_phases, _run_pipeline
from .retrieval.cache import _phase_cache_check, _phase_cache_write, _ttl_for
from .retrieval.cookies import _phase_cookies_staleness, _phase_resolve_cookies
from .retrieval.escalate.archive import (
    _ArchiveOutcome,
    _dispatch_archive,
    _escalate_archive_post_gate,
    _install_archive_payload,
    _install_gate_archive,
)
from .retrieval.escalate.browser import _escalate_browser
from .retrieval.escalate.loop import _phase_gate_and_escalate
from .retrieval.escalate.paid import _PAID_TIER_ORDER, _escalate_paid, paid_budget_available
from .retrieval.escalate.seam import Rung, _comprehend, escalate
from .retrieval.install import TierInstall, _install_rendered_fields, install
from .retrieval.tier_walk import _dispatch_action, _Exec, _install_won_tier, _phase_tier_loop, _planner_caps, _tier_is_cloudflare
from .sufficiency.completeness import _apply_llm_listing_oracle, _phase_listing_completeness
from .telemetry import _emit_tier_ended, _emit_tier_started, _format_age, _host
from .verdict.promotions import _has_browser_hint, _has_hint, _phase_complete_small_page_promotion, _phase_empty_promotion
from .verdict.terminal import _apply_terminal


async def fetch(
    url: str,
    *,
    state: AppState,
    browser_backend: Lazy[BrowserBackend] | None = None,
    browser_robust_backend: Lazy[BrowserBackend] | None = None,
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

    Emits typed phase-boundary events via `await a2web_log.info(EventInstance(...))`
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

    # Reader-prefix normalization: if the caller pre-wrapped the URL in a reader
    # service (`https://r.jina.ai/<real>`), unwrap it FIRST so `requested_url` and
    # the whole ladder operate on the true target. A pre-wrapped URL otherwise
    # pins a2web to the jina tier alone with no fallback (domain.strip_reader_prefix).
    unwrapped = strip_reader_prefix(url)
    if unwrapped is not None:
        url = unwrapped
    requested_url = url  # the caller's real target, before any rewrite

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
            BrowserBackend,
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

    deadline_s = state.settings.fetch_deadline_s
    fc = FetchContext(
        started_at=started_at,
        start_perf=start_perf,
        deadline_perf=(start_perf + deadline_s) if deadline_s > 0 else None,
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

    # v1 suggestion-uptake telemetry: only on the ask path, best-effort. Records
    # whether this ask followed an earlier suggestion + logs the targets this ask
    # now emits, so follow-through can be measured (openspec D12 / task 8.2).
    if ask is not None and state.sqlite is not None:
        await _record_uptake(fc, state)

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


# `__all__` carries the compatibility surface as well as the tree's own names:
# `fetcher.py` re-exported these to its importers, and narrowing that surface
# inside the move commit would hide a rename in a 3000-line diff.
__all__ = [
    "LENGTH_FLOOR",
    "PAID_DISPATCH_CAP",
    "REGISTRY",
    "THIN_FALLTHROUGH",
    "TIER_ORDER",
    "_ARCHIVE_MIRROR_HOSTS",
    "_COMMENT_COUNT_RE",
    "_DIGEST_GATE_SOURCES",
    "_DIGEST_LINK_CAP",
    "_INCOMPLETE_OBSTACLES",
    "_JS_EXECUTED_TIERS",
    "_JS_HEAVY_HOSTS_SEED",
    "_MENU_LABELS",
    "_PAID_TIER_ORDER",
    "_PROSE_METADATA_LD_TYPES",
    "_RENDER_CONTENT_CEILING",
    "_THIN_BROWSER_MAX_BODY",
    "Action",
    "AppSettings",
    "AsyncIterator",
    "CacheRow",
    "ContentCandidate",
    "Cookie",
    "CookiesAttached",
    "CookiesStale",
    "CorrelatedWitnessRung",
    "DeadlineExceeded",
    "Diagnostic",
    "Enum",
    "EscalateBrowser",
    "EscalatePaid",
    "EscalationSignal",
    "ExtractionMeta",
    "FetchContext",
    "GateOutcomeProjection",
    "Heading",
    "JsonPayload",
    "Link",
    "LinkDigest",
    "Literal",
    "LlmNextLink",
    "NextLink",
    "NextLinkKind",
    "Observation",
    "ObservationKind",
    "OperatorHint",
    "OtherPageBoundary",
    "PlannerCaps",
    "Record",
    "RecordSet",
    "Rendered",
    "ResourceUnavailable",
    "RetryViaArchive",
    "RewriteUrl",
    "RouterPayload",
    "RoutingOutcome",
    "Rung",
    "SqliteResource",
    "StageEnded",
    "StageStarted",
    "TerminalOutcome",
    "Tier",
    "TierEnded",
    "TierInstall",
    "TierResult",
    "TierStarted",
    "Verdict",
    "_ArchiveOutcome",
    "_Exec",
    "_ExtractResult",
    "_GateResult",
    "_apply_llm_listing_oracle",
    "_apply_terminal",
    "_build_link_digest",
    "_check_deadline",
    "_comprehend",
    "_dispatch_action",
    "_dispatch_archive",
    "_emit_tier_ended",
    "_emit_tier_started",
    "_escalate_archive_post_gate",
    "_escalate_browser",
    "_escalate_paid",
    "_escalate_via_json",
    "_escalate_via_records",
    "_format_age",
    "_has_browser_hint",
    "_has_hint",
    "_heading_link_kind",
    "_host",
    "_install_archive_payload",
    "_install_gate_archive",
    "_install_rendered_fields",
    "_install_won_tier",
    "_is_archive_mirror",
    "_is_prose_metadata_ld",
    "_listing_wants_render",
    "_normalize_ws",
    "_obstacle_wants_render",
    "_phase_answer",
    "_phase_cache_check",
    "_phase_cache_write",
    "_phase_complete_small_page_promotion",
    "_phase_cookies_staleness",
    "_phase_empty_promotion",
    "_phase_extract",
    "_phase_extract_answer",
    "_phase_gate_and_escalate",
    "_phase_listing_completeness",
    "_phase_listing_render",
    "_phase_obstacle_render",
    "_phase_resolve_cookies",
    "_phase_tier_loop",
    "_pick_display_candidate",
    "_planner_caps",
    "_record_deadline",
    "_record_discussion_link",
    "_record_uptake",
    "_records_to_next_links",
    "_regate_after_escalation",
    "_rehydrate_routing_handles",
    "_remaining_budget",
    "_rows_to_record_set",
    "_run_extraction_escalation",
    "_run_phases",
    "_run_pipeline",
    "_suppress_subsets",
    "_tier_is_cloudflare",
    "_to_llm_next_link",
    "_ttl_for",
    "_validate_llm_next_links_against_markdown",
    "_wire_content_md",
    "_within_budget",
    "aiosqlite",
    "assemble_menu",
    "asynccontextmanager",
    "asyncio",
    "build_digest",
    "build_response",
    "captcha_redirect_hint",
    "cast",
    "classify_terminal",
    "content_empty_hint",
    "content_expectations",
    "content_not_found_hint",
    "content_thin_hint",
    "cookies_stale_hint",
    "dataclass",
    "date",
    "decide_next",
    "escalate",
    "evaluate",
    "evaluate",
    "extract_json_payloads",
    "extract_markdown",
    "extract_markdown",
    "extract_records",
    "fetch",
    "fetch_deadline_hint",
    "field",
    "has_hint",
    "install",
    "is_answer_bearing",
    "is_complete_small_page",
    "is_confirmed_empty",
    "is_json_content_type",
    "js_heavy_hosts",
    "json_response_fallback",
    "json_to_markdown_rows",
    "listing_has_more",
    "listing_oracle",
    "listing_rows",
    "llm_unavailable_hint",
    "log",
    "log_warning",
    "looks_like_unrendered_spa",
    "note_visit",
    "paid_auth_error_hint",
    "paid_budget_available",
    "parse_json_response",
    "parse_metadata",
    "rank_payloads",
    "re",
    "record_suggestions",
    "replace",
    "resolve_verdict",
    "try_user_browser_hint",
    "urljoin",
    "urlparse",
]
