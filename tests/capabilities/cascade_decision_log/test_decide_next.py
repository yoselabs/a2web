"""Property + example tests for `decide_next` — the cascade-decision-log planner."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from a2web.actions import Continue, EscalateBrowser, EscalatePaid, PlannerCaps, RetryViaArchive, RewriteUrl, decide_next
from a2web.decision_log import Observation, ObservationKind
from a2web.models import Verdict
from a2web.packages.escalation import EscalationSignal

_escalations = st.sampled_from(
    [
        None,
        EscalationSignal(next_tier="browser", reason="js_required"),
        EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam"),
    ],
)
_observations = st.builds(
    Observation,
    kind=st.sampled_from(ObservationKind),
    source=st.text(max_size=12),
    verdict=st.sampled_from(Verdict),
    authoritative=st.booleans(),
    t_ms=st.integers(min_value=0, max_value=600_000),
    status_code=st.sampled_from([0, 200, 403, 404, 429, 500]),
    cloudflare=st.booleans(),
    escalation=_escalations,
)
_logs = st.lists(_observations, max_size=10)
_caps = st.builds(
    PlannerCaps,
    url_rewrites=st.integers(0, 2),
    archive_dispatches=st.integers(0, 2),
    browser_dispatches=st.integers(0, 2),
    paid_dispatches=st.integers(0, 2),
)
_urls = st.sampled_from(
    [
        "https://example.com/page",
        "https://arxiv.org/pdf/2401.12345",
        "https://www.reddit.com/r/x/comments/abc/title/",
        "https://nyt.com/article",
    ],
)

_FRESH = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=0, paid_dispatches=0)


@given(_logs, _urls, _caps)
def test_decide_next_is_total(log: list[Observation], url: str, caps: PlannerCaps) -> None:
    """Every (log, url, caps) yields exactly one valid Action."""
    action = decide_next(log, url=url, caps=caps)
    assert isinstance(action, (RetryViaArchive, RewriteUrl, EscalateBrowser, EscalatePaid, Continue))


@given(_logs, _urls, _caps)
def test_decide_next_respects_caps(log: list[Observation], url: str, caps: PlannerCaps) -> None:
    """The planner never returns an escalation whose per-fetch budget is spent."""
    action = decide_next(log, url=url, caps=caps)
    if isinstance(action, RewriteUrl):
        assert caps.url_rewrites < 1
    if isinstance(action, RetryViaArchive):
        assert caps.archive_dispatches < 1
    if isinstance(action, EscalateBrowser):
        # Browser escalates up to twice per fetch — fast Chromium rung then
        # robust CDP rung (the fast→robust ladder is this rule firing twice).
        assert caps.browser_dispatches < 2
    if isinstance(action, EscalatePaid):
        assert caps.paid_dispatches < 1


def _tier(
    verdict: Verdict,
    *,
    source: str = "raw",
    authoritative: bool = False,
    status_code: int = 200,
    cloudflare: bool = False,
    subsystem: str | None = None,
) -> Observation:
    return Observation(
        kind=ObservationKind.tier_outcome,
        source=source,
        verdict=verdict,
        authoritative=authoritative,
        t_ms=1,
        status_code=status_code,
        cloudflare=cloudflare,
        escalation=None,
        subsystem=subsystem,
    )


def _gate(verdict: Verdict, *, suggested_tier: str | None = None, subsystem: str | None = None) -> Observation:
    escalation: EscalationSignal | None = None
    if suggested_tier == "browser":
        escalation = EscalationSignal(next_tier="browser", reason="js_required")
    elif suggested_tier == "tls_impersonate":
        escalation = EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam")
    return Observation(
        kind=ObservationKind.gate_outcome,
        source="gate",
        verdict=verdict,
        authoritative=False,
        t_ms=2,
        status_code=0,
        cloudflare=False,
        escalation=escalation,
        subsystem=subsystem,
    )


def test_empty_log_continues() -> None:
    assert isinstance(decide_next([], url="https://x.com/", caps=_FRESH), Continue)


def test_arxiv_pdf_rewrites_to_abs() -> None:
    action = decide_next([_tier(Verdict.ok)], url="https://arxiv.org/pdf/2401.12345", caps=_FRESH)
    assert action == RewriteUrl(new_url="https://arxiv.org/abs/2401.12345")


def test_arxiv_rewrite_suppressed_when_cap_spent() -> None:
    caps = PlannerCaps(url_rewrites=1, archive_dispatches=0, browser_dispatches=0, paid_dispatches=0)
    action = decide_next([_tier(Verdict.ok)], url="https://arxiv.org/pdf/2401.12345", caps=caps)
    assert isinstance(action, Continue)


def test_gate_browser_signal_escalates_browser() -> None:
    log = [_tier(Verdict.ok), _gate(Verdict.anti_bot, suggested_tier="browser")]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_gate_paywall_retries_via_archive() -> None:
    log = [_tier(Verdict.ok), _gate(Verdict.paywall)]
    assert decide_next(log, url="https://nyt.com/a", caps=_FRESH) == RetryViaArchive(url="https://nyt.com/a")


def test_gate_block_page_retries_via_archive() -> None:
    log = [_tier(Verdict.ok), _gate(Verdict.block_page_detected)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), RetryViaArchive)


def test_clean_gate_continues() -> None:
    log = [_tier(Verdict.ok), _gate(Verdict.ok)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), Continue)


def test_cloudflare_403_tier_retries_via_archive() -> None:
    log = [_tier(Verdict.connection_error, status_code=403, cloudflare=True)]
    assert decide_next(log, url="https://x.com/", caps=_FRESH) == RetryViaArchive(url="https://x.com/")


def test_non_cloudflare_403_does_not_retry_archive() -> None:
    log = [_tier(Verdict.connection_error, status_code=403, cloudflare=False)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), Continue)


def test_reddit_comment_authoritative_not_found_retries_via_archive() -> None:
    """Handler-confirmed deletion (authoritative=True) → archive snapshot."""
    log = [_tier(Verdict.not_found, source="site_handler:reddit", authoritative=True, status_code=0)]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    assert decide_next(log, url=url, caps=_FRESH) == RetryViaArchive(url=url)


def test_reddit_comment_404_retries_via_archive() -> None:
    """Hard 404 from raw tier (no handler involvement) → archive snapshot."""
    log = [_tier(Verdict.not_found, source="raw", status_code=404)]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    assert decide_next(log, url=url, caps=_FRESH) == RetryViaArchive(url=url)


def test_reddit_comment_js_required_does_not_retry_archive() -> None:
    """v0.23 bench failure mode: Reddit serves a JS-shell anti-bot interstitial
    that produces non-authoritative not_found from raw, with a gate observation
    carrying subsystem='js_required'. The archive rule must NOT short-circuit;
    the page is alive and should escalate to browser instead."""
    log = [
        _gate(Verdict.length_floor, suggested_tier="browser", subsystem="js_required"),
        _tier(Verdict.not_found, source="raw", authoritative=False, status_code=200),
    ]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    action = decide_next(log, url=url, caps=_FRESH)
    assert not isinstance(action, RetryViaArchive)


def test_reddit_comment_not_found_without_evidence_does_not_retry_archive() -> None:
    """Non-authoritative not_found from raw, no 404 status, no js_required signal
    — no evidence the page is gone OR shielded. Don't dispatch archive."""
    log = [_tier(Verdict.not_found, source="raw", authoritative=False, status_code=200)]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    assert isinstance(decide_next(log, url=url, caps=_FRESH), Continue)


def test_reddit_listing_not_found_does_not_retry_archive() -> None:
    """A Reddit listing not_found does not escalate to archive — Wayback is no help."""
    log = [_tier(Verdict.not_found, source="site_handler:reddit", authoritative=True)]
    assert isinstance(decide_next(log, url="https://www.reddit.com/r/programming/", caps=_FRESH), Continue)


def test_archive_cap_spent_escalates_paid_then_suppresses() -> None:
    """Archive spent on a paywall → the paid last resort fires; once paid is
    also spent, the planner finally yields Continue (falls to the late hint)."""
    log = [_tier(Verdict.ok), _gate(Verdict.paywall)]
    caps_archive_spent = PlannerCaps(url_rewrites=0, archive_dispatches=1, browser_dispatches=0, paid_dispatches=0)
    action = decide_next(log, url="https://nyt.com/a", caps=caps_archive_spent)
    assert not isinstance(action, RetryViaArchive)  # archive suppressed
    assert isinstance(action, EscalatePaid)  # paid is the next (last) resort
    caps_all_spent = PlannerCaps(url_rewrites=0, archive_dispatches=1, browser_dispatches=0, paid_dispatches=1)
    assert isinstance(decide_next(log, url="https://nyt.com/a", caps=caps_all_spent), Continue)


def test_browser_escalates_twice_then_suppresses() -> None:
    """Fast→robust ladder: the browser rule fires at dispatch 0 (fast Chromium
    rung) and 1 (robust CDP rung), then is suppressed at 2. The same rule
    running twice IS the ladder — no second rule, no second action."""
    log = [_tier(Verdict.ok), _gate(Verdict.anti_bot, suggested_tier="browser")]

    def _at(n: int) -> object:
        # paid_dispatches=1 keeps the paid last-resort rule out of the way so
        # this test stays focused on the browser fast→robust ladder.
        caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=n, paid_dispatches=1)
        return decide_next(log, url="https://x.com/", caps=caps)

    assert isinstance(_at(0), EscalateBrowser)  # fast rung
    assert isinstance(_at(1), EscalateBrowser)  # robust rung
    assert isinstance(_at(2), Continue)  # cap spent


def test_paid_yields_to_archive_when_archive_available() -> None:
    """Paid is the LAST resort — a still-available archive retry outranks it
    (both LOW priority, archive declared earlier in _RULES)."""
    log = [_tier(Verdict.ok), _gate(Verdict.paywall)]
    action = decide_next(log, url="https://nyt.com/a", caps=_FRESH)
    assert isinstance(action, RetryViaArchive)


def test_paid_fires_on_anti_bot_after_browser_exhausted() -> None:
    """anti_bot doesn't route to archive; once the browser ladder is spent the
    paid last resort fires."""
    log = [_tier(Verdict.ok), _gate(Verdict.anti_bot, suggested_tier="browser")]
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=0)
    assert isinstance(decide_next(log, url="https://x.com/", caps=caps), EscalatePaid)


def test_paid_does_not_fire_on_success() -> None:
    """A gate-passing fetch never triggers the paid last resort."""
    log = [_tier(Verdict.ok), _gate(Verdict.ok)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), Continue)


def test_gate_browser_signal_outranks_reddit_archive_when_both_apply() -> None:
    """The structural-regression case from `planner-rules-typed-priority`:
    if both the Reddit-comment archive rule AND the gate-browser-signal rule
    could fire (counterfactually — the js_required veto on the archive rule
    already prevents conflict at the precondition level), priority must
    pick the browser-escalation rule (HIGH > MEDIUM). The veto + the
    priority ordering converge on the same outcome: browser wins, archive
    silenced."""
    from a2web.actions.playbook import EscalateBrowser, decide_next

    log = [
        _tier(Verdict.not_found, source="site_handler:reddit", authoritative=True),
        _gate(Verdict.length_floor, suggested_tier="browser"),
    ]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    action = decide_next(log, url=url, caps=_FRESH)
    assert isinstance(action, EscalateBrowser)


def test_rule_names_are_unique() -> None:
    """Adding a new PlannerRule must not collide with an existing one."""
    from a2web.actions.playbook import _RULES

    names = [r.name for r in _RULES]
    assert len(names) == len(set(names)), names


def test_decide_next_is_pure() -> None:
    """Same (log, url, caps) → same Action across repeated calls."""
    log = [_tier(Verdict.not_found, source="site_handler:reddit", authoritative=True)]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    first = decide_next(log, url=url, caps=_FRESH)
    second = decide_next(log, url=url, caps=_FRESH)
    third = decide_next(log, url=url, caps=_FRESH)
    assert first == second == third
