"""`FetchContext` — the state every pipeline stage reads and writes.

Whole on purpose. Slicing it per node is phase two of
`decompose-fetcher-into-files`, blocked until the response contract absorbs the
42-of-72 fields `fetcher_response.py` reads out of it.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from any_browser import BrowserBackend
from async_scope import Lazy
from record_mine import RecordSet

from ..actions.terminal import TerminalOutcome
from ..cache import CacheRow, SqliteResource
from ..cookie_jar import Cookie, CookieJarResource
from ..decision_log import Observation, ObservationKind, resolve_verdict
from ..hints import (
    OperatorHint,
)
from ..link_digest import LinkDigest
from ..llm_resource import LlmExtractorResource
from ..models import CacheState, DeclaredEntity, Diagnostic, ExtractionMeta, Heading, Link, NextLink, Verdict
from ..packages.escalation import EscalationSignal
from ..packages.llm_extract import RouterPayload, RoutingOutcome
from ..state import unavailable_lazy
from ..tiers import Rendered


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
    # True for Article/NewsArticle JSON-LD — a metadata echo (headline/author/
    # date) the extracted prose already carries. Kept OFF the caller-facing
    # `content_md` concatenation (task 7.2) so it never bloats above-floor prose
    # (the historical blog.html regression). Product/Org/records leave it False —
    # they ARE additive. Does NOT affect the extractor menu (it still sees all).
    is_prose_metadata: bool = False


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
    browser_robust_backend: Lazy[BrowserBackend] = field(
        default_factory=lambda: unavailable_lazy(BrowserBackend, reason="browser_robust_backend not provisioned"),
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
    # Set when the extraction provider call itself failed. Distinguishes a dead
    # backend from a genuine empty answer — both leave `extracted_answer` empty,
    # but the caller needs opposite advice for each.
    extraction_provider_error: str | None = None
    extraction_provider_error_retryable: bool = False
    # v0.21 router-shape payload — populated when `include_routing=True` and
    # the extractor returned a parseable router-shape envelope. Boundary type
    # from packages/llm_extract; projected into pydantic at the seam in
    # `fetcher_response.build_response`.
    routing: RouterPayload | None = None
    # What happened to that envelope. `None` when routing was never requested —
    # which `routing is None` alone cannot distinguish from a parse failure.
    routing_outcome: RoutingOutcome | None = None
    include_routing: bool = True
    # v1 link-affordances — the closed link-digest fed to the extractor for
    # `{{n}}` handle references; built in `_phase_extract_answer` gated on a
    # product/listing proxy. None on genres that skip the digest.
    link_digest: LinkDigest | None = None

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
    #: Age of the archive snapshot that answered, when one did (ADR-0009: the
    #: caller must be able to tell a live page from a years-old copy).
    snapshot_age_days: int | None = None
    #: The snapshot's calendar date — outlives the age, which decays on contact.
    snapshot_taken_at: date | None = None
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
    # True when `_phase_empty_promotion` confirmed a corroborated empty result
    # (`is_confirmed_empty`): the thin `length_floor` page is promoted to an `ok`
    # "no results" answer. The verdict is NOT flipped (so cache_write still declines
    # it — a promoted empty must never be cached); this flag is the single signal
    # the response builders read to override status → ok and synthesize the answer.
    empty_confirmed: bool = False
    # empty-vs-wall-discrimination sibling: True when `_phase_complete_small_page_promotion`
    # confirmed a corroborated COMPLETE small page (`is_complete_small_page`) — a thin
    # `length_floor` page whose independent browser render agreed it is small, not
    # walled. Unlike the empty flag, this ENABLES extraction (the extractor runs on the
    # real body) rather than synthesizing an answer. The verdict is left `length_floor`
    # (so cache_write declines it — never cache a wire-only promotion — and confidence
    # stays `low`); the response builder promotes status → `ok` via `small_page_promoted()`.
    small_page_confirmed: bool = False

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

    # Monotonic instant past which no further hop may be dispatched. `None`
    # disables the deadline — which is what `fetch_deadline_s <= 0` selects, and
    # also what a directly-constructed context (unit tests, the eval harness)
    # gets. Defaulted rather than required because those callers construct this
    # by hand; `fetch()` — the only production construction site — always sets
    # it from settings. Monotonic, not wall clock: a clock step must never
    # shorten or extend a fetch budget.
    deadline_perf: float | None = None

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
    # Producer-declared cache volatility, carried from the winning TierResult.
    volatility: str | None = None
    # The terminal classification `_apply_terminal` computed. CARRIED, not
    # recomputed: `fetcher_response` used to re-derive it three times by reading
    # hint CODES and SEVERITIES back out, so editing a hint's wording could
    # silently change whether a fetch reported `retrieval_incomplete`.
    terminal: TerminalOutcome | None = None
    record_count: int | None = None
    # The parsed record set itself (rank-don't-skip): retained so the ask
    # projection can surface the option shelf, instead of keeping only the count
    # and discarding the structured records. None on a non-listing page.
    record_set: RecordSet | None = None
    # What the PAGE declared itself to be, parsed from its own JSON-LD during
    # the comprehension ladder. Carried rather than re-derived at projection
    # time: `fetcher_response` must never reconstruct a decision from the
    # artifact that decision produced, and re-parsing the body there would be
    # exactly that (it would also need `raw_html`, which it does not have).
    # None when the page published no subject-level declaration.
    declared_entity: DeclaredEntity | None = None
    items_loaded: int | None = None
    items_total: int | None = None
    # The numeric oracle the regex path extracted (set even when it deemed the
    # listing complete), so the LLM-side oracle fallback fires ONLY when the
    # regex found no numeric total at all — never overriding a regex verdict
    # (content-aware refinement, LLM-side detection never suppresses a signal).
    regex_oracle_total: int | None = None
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
        subresource_blocks: int = 0,
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
                subresource_blocks=subresource_blocks,
            ),
        )

    def resolved_verdict(self) -> Verdict:
        """Project the current observation log to a verdict (pure, order-independent)."""
        return resolve_verdict(self.observations)

    def small_page_promoted(self) -> bool:
        """True when a corroborated complete-small-page is safe to serve as `ok`.

        The flag (`small_page_confirmed`) only marks the page ELIGIBLE — it enables
        extraction. The promotion to an `ok` status is granted here, read by both
        `_apply_terminal` (stand down — no `content_thin` failure hint) and
        `build_response` (status → ok). On the `query`/ask path the `ok` is granted
        only when extraction actually produced a non-empty answer; if it came back
        empty the page falls back to the honest `content_thin` failure (no silent
        miss, ADR-0009). On `fetch_raw` (no `ask`) the small body itself is the
        deliverable, so eligibility alone promotes.
        """
        if not self.small_page_confirmed:
            return False
        if self.ask is None:
            return True
        return bool((self.extracted_answer or "").strip())

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


# --------------------------------------------------------------------- #
# Per-fetch deadline
# --------------------------------------------------------------------- #


class DeadlineExceeded(Exception):
    """Raised at a dispatch boundary when the fetch budget is spent."""


def _remaining_budget(fc: FetchContext) -> float | None:
    """Seconds left on the fetch deadline, or `None` when it is disabled."""
    if fc.deadline_perf is None:
        return None
    return fc.deadline_perf - time.perf_counter()


def _check_deadline(fc: FetchContext, *, about_to: str) -> None:
    """Refuse to dispatch another hop once the budget is spent.

    Checked BEFORE each dispatch rather than enforced by cancelling mid-flight:
    a hop that is already running has usually already paid its network cost, and
    killing it converts a slow-but-succeeding fetch into a failure. What must be
    prevented is *starting* work there is no budget left to finish.
    """
    remaining = _remaining_budget(fc)
    if remaining is not None and remaining <= 0:
        raise DeadlineExceeded(about_to)


@asynccontextmanager
async def _within_budget(fc: FetchContext, *, about_to: str) -> AsyncIterator[None]:
    """Bound one hop by `min(its own timeout, the remaining fetch budget)`.

    The hop keeps its own timeout — this only caps it when less budget remains
    than the hop would otherwise take. Applied at the dispatch site rather than
    inside each tier deliberately: there are eight tiers plus the handlers, and
    a bound that has to be re-implemented nine times is a bound that will be
    missing from the tenth.
    """
    _check_deadline(fc, about_to=about_to)
    remaining = _remaining_budget(fc)
    if remaining is None:
        yield
        return
    try:
        async with asyncio.timeout(remaining):
            yield
    except TimeoutError as exc:
        raise DeadlineExceeded(about_to) from exc
