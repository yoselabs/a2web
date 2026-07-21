"""Playbook — the pure planner that maps the decision log to a follow-up action.

`decide_next` is the single policy function for the planner-driven **cascade**
escalation: given the append-only observation log, the request URL, and the
per-fetch caps, it returns exactly one `Action`, dispatched by the one unified
executor `fetcher._dispatch_action` (unify-escalation-executor). For the cascade
(tier-walk + post-gate), the orchestrator holds no escalation policy of its own.
(Phase 2 of `cascade-decision-log`.)

NOTE: the post-extraction *completeness* escalations — the obstacle-driven
render, the listing scroll render, and the handler `escalate_to_render` ladder —
are NOT yet planner rules; their policy still lives in dedicated fetcher phases.
Folding them into `decide_next` (Finding 2) is a documented follow-up change
(`single-source-escalation-policy`), which also designs the `EscalatePaid(scroll=…)`
Action variant those renders need.

Imports nothing from `a2web.fetcher` — no I/O, no circular deps.

Rule architecture: `decide_next` is an enumerator over `_RULES: tuple[PlannerRule, ...]`,
ordered by `(-priority, declaration_index)`. Each `PlannerRule` declares its
priority on the closed `RulePriority` enum and a `decide` callable that either
returns an `Action` or `None`. First non-None match wins. Order in the tuple
breaks priority ties. Adding a rule means appending to `_RULES` with a stated
priority — no need to touch sibling rules' code paths.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum

from ..decision_log import Observation, ObservationKind
from ..models import Verdict
from ..packages.block_detector import THIN_FALLTHROUGH
from .terminal import has_hard_wall_evidence, has_shell_fingerprint


@dataclass(slots=True, frozen=True)
class RetryViaArchive:
    """Dispatch the archive tier for `url` out-of-band."""

    url: str


@dataclass(slots=True, frozen=True)
class RewriteUrl:
    """Restart the tier loop with `new_url`."""

    new_url: str


@dataclass(slots=True, frozen=True)
class EscalateBrowser:
    """Dispatch the browser tier out-of-band for the current URL."""


@dataclass(slots=True, frozen=True)
class EscalatePaid:
    """Dispatch a paid tier (Zyte / Firecrawl) out-of-band — the last resort.

    Fires only after every cheaper escalation is spent: as the lowest-priority
    rule declared last, `decide_next` reaches it only when the browser rule
    (cap/verdict) and both archive rules (cap/verdict) have all returned None.
    Paid egress incurs cost, so it must never preempt a free recovery.
    """


@dataclass(slots=True, frozen=True)
class Continue:
    """No escalation — advance to the next tier, or finish the cascade."""


Action = RetryViaArchive | RewriteUrl | EscalateBrowser | EscalatePaid | Continue


@dataclass(slots=True, frozen=True)
class PlannerCaps:
    """Per-fetch escalation budgets the planner must respect.

    `url_rewrites` and `archive_dispatches` are capped at 1; `browser_dispatches`
    is capped at 2 — the fast Chromium rung then the robust CDP rung (the
    fast→robust browser ladder is the browser rule firing twice).
    `paid_dispatches` is capped at 1 — a single paid last-resort attempt per
    fetch (cost-incurring; never speculative).
    """

    url_rewrites: int
    archive_dispatches: int
    browser_dispatches: int
    paid_dispatches: int


class RulePriority(IntEnum):
    """Closed enum for planner rule precedence. Higher value outranks lower.

    Levels (chosen to be coarse — fine-grained ordering inside a level is
    declaration-order in `_RULES`):

    - CRITICAL: URL-pattern rewrites that must run before any verdict-based
      rule could fire (otherwise the tier loop runs on the wrong URL).
    - HIGH: positive escalation signals from the gate (the page is alive
      and reachable with the right tier). Outrank archive heuristics so a
      "page is gone" inference never preempts a "page needs JS" signal.
    - MEDIUM: URL-pattern + verdict heuristics that *might* indicate the
      page is gone (Reddit-comment + not_found). Below HIGH so a competing
      gate signal still wins.
    - LOW: catch-all archive heuristics (Cloudflare 403/429, gate paywall/
      block). Lowest priority — these should never preempt a more specific
      signal.
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass(slots=True, frozen=True)
class _RuleContext:
    """Input to every PlannerRule.decide — frozen view of the planner's args."""

    log: Sequence[Observation]
    last: Observation | None
    url: str
    caps: PlannerCaps


@dataclass(slots=True, frozen=True)
class PlannerRule:
    """One escalation rule. `decide` returns an Action when it applies, else None."""

    name: str
    priority: RulePriority
    decide: Callable[[_RuleContext], Action | None]


_ARXIV_PDF_RE = re.compile(r"^https?://arxiv\.org/pdf/([^/?#]+?)(?:\.pdf)?(?:[/?#].*)?$", re.IGNORECASE)
_REDDIT_COMMENT_RE = re.compile(r"^https?://(?:www\.|old\.|np\.)?reddit\.com/r/[^/]+/comments/", re.IGNORECASE)


def _decide_arxiv_pdf_rewrite(ctx: _RuleContext) -> Action | None:
    """arxiv PDF → abs-page rewrite (URL-based; fires regardless of verdict)."""
    if ctx.caps.url_rewrites >= 1:
        return None
    arxiv_match = _ARXIV_PDF_RE.match(ctx.url)
    if arxiv_match is None:
        return None
    return RewriteUrl(new_url=f"https://arxiv.org/abs/{arxiv_match.group(1)}")


def _decide_gate_browser_signal(ctx: _RuleContext) -> Action | None:
    """Gate flagged a JS-required / anti-bot page → browser.

    Fires up to twice per fetch (cap `< 2`): the first dispatch is the fast
    Chromium rung (`browser`), the second the robust CDP rung (`browser_robust`).
    A successful fast render yields `verdict == ok`, so the `verdict is not ok`
    guard stops the re-fire; only a thin/blocked fast render (gate still wants
    browser) re-triggers, escalating fast→robust. The orchestrator's single
    browser-escalation handler picks the rung from the dispatch count — the
    laddering is this same rule running twice, not a second rule.
    """
    last = ctx.last
    if last is None:
        return None
    if (
        last.kind is ObservationKind.gate_outcome
        and last.escalation is not None
        and last.escalation.next_tier == "browser"
        and last.verdict is not Verdict.ok
        and ctx.caps.browser_dispatches < 2
    ):
        return EscalateBrowser()
    return None


def _decide_reddit_comment_not_found_archive(ctx: _RuleContext) -> Action | None:
    """A Reddit comment thread is genuinely gone → archive snapshot.

    Requires two-signal evidence so the rule does not preempt browser
    escalation on live-but-JS-shielded pages (v0.23 bench failure mode).

    Discriminator:
      - "truly gone" evidence: handler-confirmed (authoritative) OR hard 404.
      - veto: any prior observation with subsystem="js_required" means the
        page is alive and just JS-shielded — let the browser-escalation
        rule (higher priority) handle it.
    """
    last = ctx.last
    if last is None:
        return None
    if (
        last.kind is ObservationKind.tier_outcome
        and last.verdict is Verdict.not_found
        and (last.authoritative or last.status_code == 404)
        and _REDDIT_COMMENT_RE.match(ctx.url) is not None
        and ctx.caps.archive_dispatches < 1
        and not any(o.subsystem == "js_required" for o in ctx.log)
    ):
        return RetryViaArchive(url=ctx.url)
    return None


def _decide_cloudflare_403_429_archive(ctx: _RuleContext) -> Action | None:
    """Cloudflare 403 / 429 from a tier → archive snapshot."""
    last = ctx.last
    if last is None:
        return None
    if last.kind is ObservationKind.tier_outcome and last.cloudflare and last.status_code in (403, 429) and ctx.caps.archive_dispatches < 1:
        return RetryViaArchive(url=ctx.url)
    return None


def _decide_gate_paywall_or_block_archive(ctx: _RuleContext) -> Action | None:
    """Gate verdict of paywall / block page → archive snapshot."""
    last = ctx.last
    if last is None:
        return None
    if (
        last.kind is ObservationKind.gate_outcome
        and last.verdict in (Verdict.paywall, Verdict.block_page_detected)
        and ctx.caps.archive_dispatches < 1
    ):
        return RetryViaArchive(url=ctx.url)
    return None


# --- Transport / status escalation (the catch-all floor) ------------------
#
# A bare transport/status tier failure (403, 5xx, other-4xx, timeout, a network
# drop, an uncorroborated 404, an exhausted 429) is AMBIGUOUS: a WAF forges any
# of these to shed anonymous scrapers, so a status code alone must never end the
# cascade. These rules route every ambiguous class into `EscalateBrowser` — the
# free self-hosted rung — so no URL falls off the tree without the browser (and,
# via `paid_last_resort`, paid) having been attempted (ADR-0009).
#
# They sit at LOW priority, declared AFTER the specific archive heuristics and
# BEFORE `paid_last_resort`, so a more-specific content/gate/archive signal
# always wins and browser is always tried before paid egress. Each reads only the
# `(verdict, status_code)` already on the last tier observation — no new tier
# verdicts. Three failures are deliberately NOT here (they stay terminal): a
# genuine `dns_error` (a distinct verdict — a real browser can't resolve a dead
# domain), an authoritative `not_found` (a site handler modelling real "gone"
# semantics), and `proxy_unavailable` (local proxy-pool exhaustion, handled at
# the proxy layer, not a site wall) — each is simply not `connection_error`, so
# no rule below matches it.


def _last_tier_failure(ctx: _RuleContext) -> Observation | None:
    """The last observation iff it is a tier failure with browser budget to spend.

    The shared guard for every transport rule: the discriminator is a
    `tier_outcome` observation, and the browser cap (`< 2`) makes the rules
    unable to re-fire past the fast→robust browser ladder.
    """
    last = ctx.last
    if last is None or last.kind is not ObservationKind.tier_outcome:
        return None
    if ctx.caps.browser_dispatches >= 2:
        return None
    return last


def _decide_forbidden_403_escalate(ctx: _RuleContext) -> Action | None:
    """A 403 is anti-bot by default (near-certain) → browser."""
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.connection_error and last.status_code == 403:
        return EscalateBrowser()
    return None


def _decide_server_5xx_escalate(ctx: _RuleContext) -> Action | None:
    """A 5xx is ambiguous (a fake outage is a real WAF tactic) → browser."""
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.connection_error and last.status_code >= 500:
        return EscalateBrowser()
    return None


def _decide_other_4xx_escalate(ctx: _RuleContext) -> Action | None:
    """Any other 4xx (excl. 403; 404/429 are their own verdicts) → browser.

    401/451 are NOT carved out: a WAF issues them too, and the capped browser
    attempt costs little; a genuine auth wall still ends in the loud terminal.
    """
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.connection_error and 400 <= last.status_code < 500 and last.status_code != 403:
        return EscalateBrowser()
    return None


def _decide_timeout_escalate(ctx: _RuleContext) -> Action | None:
    """A timeout is ambiguous (tarpitting) → browser."""
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.timeout:
        return EscalateBrowser()
    return None


def _decide_network_drop_escalate(ctx: _RuleContext) -> Action | None:
    """A status-0 connection/TLS drop that is NOT DNS → browser.

    `dns_error` is a distinct verdict (terminal) and `proxy_unavailable` is its
    own verdict too, so both are excluded by the `connection_error` check — only
    a genuine network-layer block (reset / TLS handshake drop, a JA3/JA4 shed)
    reaches here, and a real browser may pass it.
    """
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.connection_error and last.status_code == 0:
        return EscalateBrowser()
    return None


def _decide_uncorroborated_404_escalate(ctx: _RuleContext) -> Action | None:
    """A non-authoritative 404 (soft-404 anti-scraping) → browser.

    An AUTHORITATIVE `not_found` (a site handler modelling the site's real "gone"
    semantics) is excluded and stays terminal. Declared below the MEDIUM
    Reddit-comment archive rule, so a genuinely-gone Reddit thread still routes to
    archive rather than a wasted browser render.
    """
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.not_found and not last.authoritative:
        return EscalateBrowser()
    return None


def _decide_exhausted_429_escalate(ctx: _RuleContext) -> Action | None:
    """A rate_limited verdict (the tier already spent its retry/backoff) → browser.

    Generalizes the prior search/listing-only 429 render escalation to every URL
    shape. A Cloudflare 429 is handled by the earlier-declared archive rule (more
    specific); this is the catch-all for a bare 429 from any tier.
    """
    last = _last_tier_failure(ctx)
    if last is not None and last.verdict is Verdict.rate_limited:
        return EscalateBrowser()
    return None


def _decide_gate_thin_escalate(ctx: _RuleContext) -> Action | None:
    """A bare thin/other gate verdict → the free browser, before conceding.

    The gate-side twin of the transport catch-all floor. A `length_floor` /
    `other` gate outcome carrying NO escalation fingerprint would otherwise end
    the cascade with only the caller-facing `try_user_browser` hint — a2web
    prescribing the caller's browser without ever trying its own. This is exactly
    the jina-reader hole: r.jina.ai returns STRIPPED MARKDOWN, so the block
    detector's browser-triggering HTML fingerprints (`js_required` needs
    `<script>`+root markers, `blank_page` needs near-empty visible text) cannot
    match, and a thinly-rendered SPA falls to the fingerprint-less `length_floor`
    bucket (`escalation=None`, `subsystem=None`). Route it to the free browser
    rung (cap `< 2`, fast→robust) so no passable wall is conceded unattempted
    (ADR-0009: "a wall is an unfinished job").

    Declared at LOW priority BEFORE `paid_last_resort`, so a more specific gate /
    archive / transport signal always wins and the free browser is always tried
    before paid egress. A bare `length_floor` stays NOT paid-worthy
    (`_is_paid_worthy_wall`), so once the browser budget is spent the cascade
    falls through to the honest terminal hint — the browser is the only new
    attempt this rule adds, never paid spend on a genuinely-short page.
    """
    last = ctx.last
    if last is None:
        return None
    if last.kind is not ObservationKind.gate_outcome or last.verdict not in (Verdict.length_floor, Verdict.other):
        return None
    # empty-vs-wall-discrimination (design decision 4): a bare thin fallthrough
    # (a short, marker-free page with NO shell/wall fingerprint anywhere in the log)
    # gets EXACTLY ONE browser render — the corroborating witness `is_complete_small_page`
    # needs; a second only re-confirms the page is small (wasted proxy render). A floor
    # violation carrying wall/empty/shell suspicion (`other`, a `length_floor` NOT
    # marked `THIN_FALLTHROUGH`, or a fetch whose log holds a `js_required`/shell
    # fingerprint — e.g. an under-rendered SPA whose markdown regate lost the
    # fingerprint) keeps the full fast→robust budget so the distinct robust engine
    # still gets its attempt.
    is_bare_thin = (
        last.verdict is Verdict.length_floor
        and last.subsystem == THIN_FALLTHROUGH
        and not has_shell_fingerprint(ctx.log)
        and not has_hard_wall_evidence(ctx.log)
    )
    cap = 1 if is_bare_thin else 2
    if ctx.caps.browser_dispatches < cap:
        return EscalateBrowser()
    return None


# Content-wall verdicts a paid last-resort tier can plausibly pass. Kept as its
# own tuple to preserve the no-import-from-fetcher invariant of the playbook
# module (fetcher's never-silently-miss floor is a separate, broader concern).
_PAID_WALL_VERDICTS = (Verdict.paywall, Verdict.block_page_detected, Verdict.anti_bot, Verdict.blank_page)


def _is_paid_worthy_wall(obs: Observation) -> bool:
    """Is this gate outcome a wall a paid render could plausibly pass?

    The three hard walls (`_PAID_WALL_VERDICTS`) qualify unconditionally. A
    `length_floor` qualifies ONLY when the block detector fingerprinted the body
    as a JS-required SPA shell (`subsystem == "js_required"`) — the paid render
    (Zyte `browserHtml`) is proven to render these. A bare `length_floor` (a
    thin page, an empty result set) is NOT paid-worthy: gating paid egress on the
    subsystem keeps spend scoped to genuine SPAs, never every short page.
    """
    if obs.verdict in _PAID_WALL_VERDICTS:
        return True
    return obs.verdict is Verdict.length_floor and obs.subsystem == "js_required"


def _decide_paid_last_resort(ctx: _RuleContext) -> Action | None:
    """Terminal wall after every free escalation is spent → paid tier.

    Declared LAST at LOW priority, so `decide_next` reaches this rule only when
    the browser rule (HIGH) and both archive rules (LOW, earlier in `_RULES`)
    have all returned None — i.e. the free/proxied ladder is genuinely
    exhausted. Keys on the latest gate/regate verdict still being a wall and the
    single paid budget being unspent. The orchestrator's `_escalate_paid` is a
    no-op when no paid tier is registered (un-keyed), so this rule is safe to
    fire unconditionally — an un-keyed deployment simply falls through to the
    late never-silently-miss hint.
    """
    last = ctx.last
    if last is None:
        return None
    if last.kind is ObservationKind.gate_outcome and _is_paid_worthy_wall(last) and ctx.caps.paid_dispatches < 1:
        return EscalatePaid()
    return None


# Ordered by (-priority, declaration_index). When two rules share a priority,
# the one earlier in the tuple wins. Append new rules in declaration order;
# the enumerator below stably sorts by negative-priority so order is preserved
# inside each priority level.
_RULES: tuple[PlannerRule, ...] = (
    PlannerRule(name="arxiv_pdf_rewrite", priority=RulePriority.CRITICAL, decide=_decide_arxiv_pdf_rewrite),
    PlannerRule(name="gate_browser_signal", priority=RulePriority.HIGH, decide=_decide_gate_browser_signal),
    PlannerRule(
        name="reddit_comment_not_found_archive",
        priority=RulePriority.MEDIUM,
        decide=_decide_reddit_comment_not_found_archive,
    ),
    PlannerRule(
        name="cloudflare_403_429_archive",
        priority=RulePriority.LOW,
        decide=_decide_cloudflare_403_429_archive,
    ),
    PlannerRule(
        name="gate_paywall_or_block_archive",
        priority=RulePriority.LOW,
        decide=_decide_gate_paywall_or_block_archive,
    ),
    # Transport/status catch-all floor (LOW): declared AFTER the specific archive
    # heuristics so a Cloudflare 403/429 still routes to archive, and BEFORE
    # `paid_last_resort` so the free browser is always tried before paid egress.
    PlannerRule(name="forbidden_403_escalate", priority=RulePriority.LOW, decide=_decide_forbidden_403_escalate),
    PlannerRule(name="server_5xx_escalate", priority=RulePriority.LOW, decide=_decide_server_5xx_escalate),
    PlannerRule(name="other_4xx_escalate", priority=RulePriority.LOW, decide=_decide_other_4xx_escalate),
    PlannerRule(name="timeout_escalate", priority=RulePriority.LOW, decide=_decide_timeout_escalate),
    PlannerRule(name="network_drop_escalate", priority=RulePriority.LOW, decide=_decide_network_drop_escalate),
    PlannerRule(name="uncorroborated_404_escalate", priority=RulePriority.LOW, decide=_decide_uncorroborated_404_escalate),
    PlannerRule(name="exhausted_429_escalate", priority=RulePriority.LOW, decide=_decide_exhausted_429_escalate),
    # Gate-side catch-all floor (LOW): a bare thin/other gate verdict with no
    # escalation fingerprint (the jina-stripped-markdown hole) → free browser.
    # Declared AFTER the transport rules and BEFORE `paid_last_resort` so the
    # free browser is always tried before paid egress, and a bare length_floor
    # never reaches paid (it stays not paid-worthy).
    PlannerRule(name="gate_thin_escalate", priority=RulePriority.LOW, decide=_decide_gate_thin_escalate),
    # Declared LAST: the paid last resort only fires when every rule above
    # returns None (free/proxied ladder + browser + archive all exhausted).
    PlannerRule(
        name="paid_last_resort",
        priority=RulePriority.LOW,
        decide=_decide_paid_last_resort,
    ),
)

# Invariant: every rule name in _RULES is unique. Test-asserted in
# `tests/capabilities/cascade_decision_log/test_decide_next.py::test_rule_names_are_unique`
# (runtime `assert` would be stripped under -O and is bandit-flagged).


def decide_next(log: Sequence[Observation], *, url: str, caps: PlannerCaps) -> Action:
    """Choose the orchestrator's next action from the decision log.

    Pure and total — every input yields exactly one `Action`. Enumerates
    `_RULES` in `(-priority, declaration_index)` order; returns the first
    non-None action. Empty log returns `Continue` directly (no observation
    means nothing to escalate on).
    """
    if not log:
        return Continue()
    ctx = _RuleContext(log=log, last=log[-1], url=url, caps=caps)
    # `sorted` is stable, so equal priorities preserve declaration order in _RULES.
    for rule in sorted(_RULES, key=lambda r: -int(r.priority)):
        action = rule.decide(ctx)
        if action is not None:
            return action
    return Continue()


__all__ = [
    "Action",
    "Continue",
    "EscalateBrowser",
    "EscalatePaid",
    "PlannerCaps",
    "PlannerRule",
    "RetryViaArchive",
    "RewriteUrl",
    "RulePriority",
    "decide_next",
]
