"""Property + example tests for `decide_next` — the cascade-decision-log planner."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from a2web.actions import Continue, EscalateBrowser, PlannerCaps, RetryViaArchive, RewriteUrl, decide_next
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
)
_urls = st.sampled_from(
    [
        "https://example.com/page",
        "https://arxiv.org/pdf/2401.12345",
        "https://www.reddit.com/r/x/comments/abc/title/",
        "https://nyt.com/article",
    ],
)

_FRESH = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=0)


@given(_logs, _urls, _caps)
def test_decide_next_is_total(log: list[Observation], url: str, caps: PlannerCaps) -> None:
    """Every (log, url, caps) yields exactly one valid Action."""
    action = decide_next(log, url=url, caps=caps)
    assert isinstance(action, (RetryViaArchive, RewriteUrl, EscalateBrowser, Continue))


@given(_logs, _urls, _caps)
def test_decide_next_respects_caps(log: list[Observation], url: str, caps: PlannerCaps) -> None:
    """The planner never returns an escalation whose per-fetch budget is spent."""
    action = decide_next(log, url=url, caps=caps)
    if isinstance(action, RewriteUrl):
        assert caps.url_rewrites < 1
    if isinstance(action, RetryViaArchive):
        assert caps.archive_dispatches < 1
    if isinstance(action, EscalateBrowser):
        assert caps.browser_dispatches < 1


def _tier(
    verdict: Verdict,
    *,
    source: str = "raw",
    authoritative: bool = False,
    status_code: int = 200,
    cloudflare: bool = False,
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
    )


def _gate(verdict: Verdict, *, suggested_tier: str | None = None) -> Observation:
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
    )


def test_empty_log_continues() -> None:
    assert isinstance(decide_next([], url="https://x.com/", caps=_FRESH), Continue)


def test_arxiv_pdf_rewrites_to_abs() -> None:
    action = decide_next([_tier(Verdict.ok)], url="https://arxiv.org/pdf/2401.12345", caps=_FRESH)
    assert action == RewriteUrl(new_url="https://arxiv.org/abs/2401.12345")


def test_arxiv_rewrite_suppressed_when_cap_spent() -> None:
    caps = PlannerCaps(url_rewrites=1, archive_dispatches=0, browser_dispatches=0)
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


def test_reddit_comment_not_found_retries_via_archive() -> None:
    log = [_tier(Verdict.not_found, source="site_handler:reddit", authoritative=True, status_code=0)]
    url = "https://www.reddit.com/r/x/comments/abc/title/"
    assert decide_next(log, url=url, caps=_FRESH) == RetryViaArchive(url=url)


def test_reddit_listing_not_found_does_not_retry_archive() -> None:
    """A Reddit listing not_found does not escalate to archive — Wayback is no help."""
    log = [_tier(Verdict.not_found, source="site_handler:reddit", authoritative=True)]
    assert isinstance(decide_next(log, url="https://www.reddit.com/r/programming/", caps=_FRESH), Continue)


def test_archive_cap_spent_suppresses_retry() -> None:
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=1, browser_dispatches=0)
    log = [_tier(Verdict.ok), _gate(Verdict.paywall)]
    assert isinstance(decide_next(log, url="https://nyt.com/a", caps=caps), Continue)


def test_browser_cap_spent_suppresses_escalation() -> None:
    caps = PlannerCaps(url_rewrites=0, archive_dispatches=0, browser_dispatches=1)
    log = [_tier(Verdict.ok), _gate(Verdict.anti_bot, suggested_tier="browser")]
    assert isinstance(decide_next(log, url="https://x.com/", caps=caps), Continue)
