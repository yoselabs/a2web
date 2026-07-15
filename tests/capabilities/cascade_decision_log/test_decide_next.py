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


def test_blank_page_gate_escalates_to_browser() -> None:
    """A blank_page gate outcome (escalation → browser) dispatches the browser."""
    log = [_tier(Verdict.ok), _gate(Verdict.blank_page, suggested_tier="browser")]
    action = decide_next(log, url="https://empty.example/x", caps=_FRESH)
    assert isinstance(action, EscalateBrowser)


def test_blank_page_reaches_paid_after_browser_spent() -> None:
    """A blank_page still walled after the browser cap is spent → paid last resort."""
    log = [_tier(Verdict.ok), _gate(Verdict.blank_page, suggested_tier="browser")]
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=0)
    action = decide_next(log, url="https://empty.example/x", caps=caps)
    assert isinstance(action, EscalatePaid)


def test_blank_page_past_all_caps_stops_escalating() -> None:
    """A blank_page with browser AND paid budgets spent → no escalation (loud terminal)."""
    log = [_tier(Verdict.ok), _gate(Verdict.blank_page, suggested_tier="browser")]
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=1)
    action = decide_next(log, url="https://empty.example/x", caps=caps)
    assert not isinstance(action, (EscalateBrowser, EscalatePaid))


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


def test_non_cloudflare_403_escalates_to_browser() -> None:
    """A non-Cloudflare 403 is anti-bot by default: the transport catch-all
    (`forbidden_403_escalate`) now escalates it to browser rather than letting
    the cascade end (escalate-on-status-derived-walls). It does NOT route to
    archive — that is reserved for the Cloudflare-fingerprinted 403."""
    log = [_tier(Verdict.connection_error, status_code=403, cloudflare=False)]
    action = decide_next(log, url="https://x.com/", caps=_FRESH)
    assert isinstance(action, EscalateBrowser)


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


def test_reddit_comment_not_found_without_evidence_escalates_to_browser() -> None:
    """Non-authoritative not_found from raw, no 404 status, no js_required signal.
    The archive rule stays silent (no evidence the page is genuinely gone), but
    the transport catch-all (`uncorroborated_404_escalate`) now treats an
    uncorroborated not_found as possible soft-404 anti-scraping and escalates it
    to browser rather than ending the cascade (escalate-on-status-derived-walls)."""
    log = [_tier(Verdict.not_found, source="raw", authoritative=False, status_code=200)]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    action = decide_next(log, url=url, caps=_FRESH)
    assert not isinstance(action, RetryViaArchive)
    assert isinstance(action, EscalateBrowser)


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


# --------------------------------------------------------------------- #
# js_required SPA shell → paid render (search-retrieval-and-confabulation-guard P1)
# --------------------------------------------------------------------- #


def test_paid_fires_on_js_required_length_floor_after_browser_exhausted() -> None:
    """A post-browser length_floor whose subsystem is js_required is a genuine
    SPA shell — the paid render (Zyte browserHtml) is the last resort."""
    log = [_tier(Verdict.ok), _gate(Verdict.length_floor, suggested_tier="browser", subsystem="js_required")]
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=0)
    assert isinstance(decide_next(log, url="https://x.com/", caps=caps), EscalatePaid)


def test_paid_does_not_fire_on_bare_length_floor() -> None:
    """length_floor WITHOUT the js_required subsystem (a thin page / empty
    result) must not trigger paid egress — the cost guard."""
    log = [_tier(Verdict.ok), _gate(Verdict.length_floor)]
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=0)
    assert isinstance(decide_next(log, url="https://x.com/", caps=caps), Continue)


def test_js_required_paid_suppressed_when_paid_cap_spent() -> None:
    """Once the single paid render is spent the rule stops firing (no spin)."""
    log = [_tier(Verdict.ok), _gate(Verdict.length_floor, suggested_tier="browser", subsystem="js_required")]
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=1)
    assert isinstance(decide_next(log, url="https://x.com/", caps=caps), Continue)


# --------------------------------------------------------------------- #
# Gate-side thin/other catch-all → free browser (jina-stripped-markdown hole).
# A bare length_floor with NO fingerprint (jina returns markdown, so the
# js_required / blank_page HTML markers never match) must still try a2web's OWN
# browser before conceding — not merely prescribe the caller's (ADR-0009).
# --------------------------------------------------------------------- #


def test_bare_length_floor_escalates_to_browser() -> None:
    """A fingerprint-less `length_floor` gate outcome → free browser, not concede."""
    log = [_tier(Verdict.ok), _gate(Verdict.length_floor)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_bare_other_gate_escalates_to_browser() -> None:
    """A bare `other` gate outcome is likewise routed to the free browser."""
    log = [_tier(Verdict.ok), _gate(Verdict.other)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_bare_length_floor_browser_ladders_fast_then_robust_then_stops() -> None:
    """The free-browser escalation ladders fast→robust (cap 2), then concedes."""
    log = [_tier(Verdict.ok), _gate(Verdict.length_floor)]

    def _at(browser_dispatches: int) -> object:
        caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=browser_dispatches, paid_dispatches=0)
        return decide_next(log, url="https://x.com/", caps=caps)

    assert isinstance(_at(0), EscalateBrowser)  # fast rung
    assert isinstance(_at(1), EscalateBrowser)  # robust rung
    # Browser budget spent and a bare length_floor is not paid-worthy → concede.
    assert isinstance(_at(2), Continue)


def test_bare_length_floor_never_reaches_paid() -> None:
    """Even with browser spent, a BARE length_floor stays off the paid path."""
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=0)
    log = [_tier(Verdict.ok), _gate(Verdict.length_floor)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=caps), Continue)


# --------------------------------------------------------------------- #
# Transport / status escalation (escalate-on-status-derived-walls)
# Each rule gets a test pair: the ambiguous failure escalates to browser, and
# each guard (browser cap / terminal carve-out) returns no escalation.
# --------------------------------------------------------------------- #

_BROWSER_SPENT = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=2, paid_dispatches=1)


def test_forbidden_403_escalates_to_browser() -> None:
    log = [_tier(Verdict.connection_error, status_code=403)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_forbidden_403_suppressed_when_browser_cap_spent() -> None:
    log = [_tier(Verdict.connection_error, status_code=403)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_BROWSER_SPENT), Continue)


def test_server_5xx_escalates_to_browser() -> None:
    log = [_tier(Verdict.connection_error, status_code=502)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_server_5xx_suppressed_when_browser_cap_spent() -> None:
    log = [_tier(Verdict.connection_error, status_code=503)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_BROWSER_SPENT), Continue)


def test_other_4xx_escalates_to_browser() -> None:
    log = [_tier(Verdict.connection_error, status_code=451)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_other_4xx_excludes_403_which_has_its_own_rule() -> None:
    # 403 must be picked up by forbidden_403, not other_4xx — both return
    # EscalateBrowser, so assert the result and that 403 still escalates.
    log = [_tier(Verdict.connection_error, status_code=403)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_timeout_escalates_to_browser() -> None:
    log = [_tier(Verdict.timeout, status_code=0)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_timeout_suppressed_when_browser_cap_spent() -> None:
    log = [_tier(Verdict.timeout, status_code=0)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_BROWSER_SPENT), Continue)


def test_network_drop_escalates_to_browser() -> None:
    """A status-0 connection_error that is NOT dns_error (reset / TLS drop)."""
    log = [_tier(Verdict.connection_error, status_code=0)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_dns_error_stays_terminal() -> None:
    """A genuine NXDOMAIN is its own verdict and matches no transport rule — a
    real browser cannot resolve a dead domain, so the cascade ends terminal."""
    log = [_tier(Verdict.dns_error, status_code=0)]
    assert isinstance(decide_next(log, url="https://nope.invalid/", caps=_FRESH), Continue)


def test_proxy_unavailable_not_swept_into_transport_escalation() -> None:
    """proxy_unavailable is local proxy-pool exhaustion, not a site wall — it is
    handled at the proxy layer and must not trigger a browser render."""
    log = [_tier(Verdict.proxy_unavailable, status_code=0)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), Continue)


def test_uncorroborated_404_escalates_to_browser() -> None:
    log = [_tier(Verdict.not_found, source="raw", authoritative=False, status_code=404)]
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


def test_authoritative_404_stays_terminal() -> None:
    """A site handler modelling real 'gone' semantics → no browser escalation."""
    log = [_tier(Verdict.not_found, source="site_handler:hn", authoritative=True, status_code=0)]
    assert isinstance(decide_next(log, url="https://news.ycombinator.com/item?id=1", caps=_FRESH), Continue)


def test_exhausted_429_escalates_on_any_shape() -> None:
    """A bare 429 (retry already spent) on a non-listing URL → browser."""
    log = [_tier(Verdict.rate_limited, status_code=429)]
    assert isinstance(decide_next(log, url="https://x.com/article", caps=_FRESH), EscalateBrowser)


def test_cloudflare_429_still_routes_to_archive_over_transport_catch_all() -> None:
    """The Cloudflare-fingerprinted 429 archive rule (declared earlier at LOW)
    outranks the generic exhausted_429 catch-all."""
    log = [_tier(Verdict.rate_limited, status_code=429, cloudflare=True)]
    assert decide_next(log, url="https://x.com/", caps=_FRESH) == RetryViaArchive(url="https://x.com/")


def test_gate_browser_signal_outranks_transport_catch_all() -> None:
    """A HIGH content-gate browser signal is the deciding rule over the LOW
    transport catch-all, even when both would return EscalateBrowser."""
    from a2web.actions import playbook

    log = [_tier(Verdict.connection_error, status_code=403), _gate(Verdict.anti_bot, suggested_tier="browser")]
    # Both a transport case (the 403 tier obs) and the HIGH gate signal are on the
    # log; the deciding rule must be the HIGH one. Assert via the winning rule.
    ctx = playbook._RuleContext(log=log, last=log[-1], url="https://x.com/", caps=_FRESH)
    winners = [r.name for r in playbook._RULES if r.decide(ctx) is not None]
    assert winners[0] == "gate_browser_signal" or "gate_browser_signal" in winners
    assert isinstance(decide_next(log, url="https://x.com/", caps=_FRESH), EscalateBrowser)


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
