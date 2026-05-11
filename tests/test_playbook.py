"""Playbook unit tests — pure rule dispatch, no I/O."""

from __future__ import annotations

from a2web.actions.playbook import (
    RetryViaArchive,
    RewriteUrl,
    next_action_after_gate,
    next_action_after_tier,
)
from a2web.models import Verdict

# AppSettings no longer needed
from a2web.tiers import TierResult


def _result(*, status_code: int = 200, headers: dict[str, str] | None = None) -> TierResult:
    return TierResult(
        body=b"",
        content_type="text/html",
        status_code=status_code,
        final_url="https://x",
        headers=headers or {},
    )


def test_paywall_triggers_archive() -> None:
    action = next_action_after_gate(Verdict.paywall, "https://nyt.com/article")
    assert action == RetryViaArchive(url="https://nyt.com/article")


def test_block_page_triggers_archive() -> None:
    action = next_action_after_gate(Verdict.block_page_detected, "https://x.com")
    assert action == RetryViaArchive(url="https://x.com")


def test_ok_gate_returns_none() -> None:
    assert next_action_after_gate(Verdict.ok, "https://x.com") is None


def test_length_floor_returns_none() -> None:
    assert next_action_after_gate(Verdict.length_floor, "https://x.com") is None


def test_cloudflare_403_triggers_archive() -> None:
    res = _result(status_code=403, headers={"cf-ray": "abc-123"})
    action = next_action_after_tier(res, "https://x.com")
    assert action == RetryViaArchive(url="https://x.com")


def test_cloudflare_429_triggers_archive() -> None:
    res = _result(status_code=429, headers={"server": "cloudflare"})
    action = next_action_after_tier(res, "https://x.com")
    assert action == RetryViaArchive(url="https://x.com")


def test_non_cloudflare_403_no_action() -> None:
    res = _result(status_code=403, headers={"server": "nginx"})
    assert next_action_after_tier(res, "https://x.com") is None


def test_arxiv_pdf_rewrite() -> None:
    res = _result(status_code=200)
    action = next_action_after_tier(res, "https://arxiv.org/pdf/2401.12345")
    assert action == RewriteUrl(new_url="https://arxiv.org/abs/2401.12345")


def test_arxiv_pdf_with_extension_rewrite() -> None:
    res = _result(status_code=200)
    action = next_action_after_tier(res, "https://arxiv.org/pdf/2401.12345.pdf")
    assert action == RewriteUrl(new_url="https://arxiv.org/abs/2401.12345")


def test_unrelated_url_no_action() -> None:
    res = _result(status_code=200)
    assert next_action_after_tier(res, "https://example.com/") is None
