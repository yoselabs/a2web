"""Playbook — the pure planner that maps the decision log to a follow-up action.

`decide_next` is the single escalation-policy function: given the append-only
observation log, the request URL, and the per-fetch caps, it returns exactly
one `Action`. The orchestrator is a pure executor of that action — it holds no
escalation policy of its own. (Phase 2 of `cascade-decision-log`.)

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
class Continue:
    """No escalation — advance to the next tier, or finish the cascade."""


Action = RetryViaArchive | RewriteUrl | EscalateBrowser | Continue


@dataclass(slots=True, frozen=True)
class PlannerCaps:
    """Per-fetch escalation budgets the planner must respect (each capped at 1)."""

    url_rewrites: int
    archive_dispatches: int
    browser_dispatches: int


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
    """Gate flagged a JS-required / anti-bot page → browser."""
    last = ctx.last
    if last is None:
        return None
    if (
        last.kind is ObservationKind.gate_outcome
        and last.escalation is not None
        and last.escalation.next_tier == "browser"
        and last.verdict is not Verdict.ok
        and ctx.caps.browser_dispatches < 1
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
    if (
        last.kind is ObservationKind.tier_outcome
        and last.cloudflare
        and last.status_code in (403, 429)
        and ctx.caps.archive_dispatches < 1
    ):
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
    "PlannerCaps",
    "PlannerRule",
    "RetryViaArchive",
    "RewriteUrl",
    "RulePriority",
    "decide_next",
]
