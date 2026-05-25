"""Playbook — the pure planner that maps the decision log to a follow-up action.

`decide_next` is the single escalation-policy function: given the append-only
observation log, the request URL, and the per-fetch caps, it returns exactly
one `Action`. The orchestrator is a pure executor of that action — it holds no
escalation policy of its own. (Phase 2 of `cascade-decision-log`.)

Imports nothing from `a2web.fetcher` — no I/O, no circular deps.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

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


_ARXIV_PDF_RE = re.compile(r"^https?://arxiv\.org/pdf/([^/?#]+?)(?:\.pdf)?(?:[/?#].*)?$", re.IGNORECASE)
_REDDIT_COMMENT_RE = re.compile(r"^https?://(?:www\.|old\.|np\.)?reddit\.com/r/[^/]+/comments/", re.IGNORECASE)


def decide_next(log: Sequence[Observation], *, url: str, caps: PlannerCaps) -> Action:
    """Choose the orchestrator's next action from the decision log.

    Pure and total — every input yields exactly one `Action`. Consulted after
    each tier observation and after the gate; the most recent observation
    drives tier-vs-gate rules, while URL-based rules fire regardless. Each
    escalation is capped at one dispatch per fetch.
    """
    if not log:
        return Continue()
    last = log[-1]

    # arxiv PDF → abs-page rewrite (URL-based; fires regardless of verdict).
    arxiv_match = _ARXIV_PDF_RE.match(url)
    if arxiv_match is not None and caps.url_rewrites < 1:
        return RewriteUrl(new_url=f"https://arxiv.org/abs/{arxiv_match.group(1)}")

    # Gate flagged a JS-required / anti-bot page → browser.
    if (
        last.kind is ObservationKind.gate_outcome
        and last.escalation is not None
        and last.escalation.next_tier == "browser"
        and last.verdict is not Verdict.ok
        and caps.browser_dispatches < 1
    ):
        return EscalateBrowser()

    # Cloudflare 403 / 429 from a tier → archive snapshot.
    if last.kind is ObservationKind.tier_outcome and last.cloudflare and last.status_code in (403, 429) and caps.archive_dispatches < 1:
        return RetryViaArchive(url=url)

    # A Reddit comment thread is genuinely gone → archive snapshot. Requires
    # two-signal evidence so the rule does not preempt browser escalation on
    # live-but-JS-shielded pages (v0.23 bench failure mode: Reddit serves an
    # anti-bot JS interstitial that produces non-authoritative not_found from
    # raw, gate stamps subsystem="js_required" on a separate observation;
    # without the veto the archive rule would short-circuit and the
    # browser-escalation signal would be ignored).
    #
    # Discriminator:
    #   - "truly gone" evidence: handler-confirmed (authoritative) OR hard 404.
    #   - veto: any prior observation with subsystem="js_required" means the
    #     page is alive and just JS-shielded — let EscalateBrowser handle it.
    #
    # The broader pattern (typed-priority planner rules) is tracked in the
    # deferred `planner-rules-typed-priority` proposal.
    if (
        last.kind is ObservationKind.tier_outcome
        and last.verdict is Verdict.not_found
        and (last.authoritative or last.status_code == 404)
        and _REDDIT_COMMENT_RE.match(url) is not None
        and caps.archive_dispatches < 1
        and not any(o.subsystem == "js_required" for o in log)
    ):
        return RetryViaArchive(url=url)

    # Gate verdict of paywall / block page → archive snapshot.
    if (
        last.kind is ObservationKind.gate_outcome
        and last.verdict in (Verdict.paywall, Verdict.block_page_detected)
        and caps.archive_dispatches < 1
    ):
        return RetryViaArchive(url=url)

    return Continue()


__all__ = [
    "Action",
    "Continue",
    "EscalateBrowser",
    "PlannerCaps",
    "RetryViaArchive",
    "RewriteUrl",
    "decide_next",
]
