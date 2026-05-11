"""Playbook — pure rules mapping tier/gate verdicts to follow-up actions.

Imports nothing from `a2web.fetcher` or `a2web.tiers` (no I/O, no
circular deps). The orchestrator consults these functions between
phases and dispatches the returned Action under per-fetch caps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Verdict

if TYPE_CHECKING:
    from ..tiers import TierResult


@dataclass(slots=True, frozen=True)
class RetryViaArchive:
    url: str


@dataclass(slots=True, frozen=True)
class RewriteUrl:
    new_url: str


@dataclass(slots=True, frozen=True)
class Skip:
    reason: str


Action = RetryViaArchive | RewriteUrl | Skip


_ARXIV_PDF_RE = re.compile(r"^https?://arxiv\.org/pdf/([^/?#]+?)(?:\.pdf)?(?:[/?#].*)?$", re.IGNORECASE)


def _is_cloudflare(tier_result: TierResult) -> bool:
    server = tier_result.headers.get("server", "").lower()
    if "cloudflare" in server:
        return True
    if "cf-ray" in tier_result.headers:
        return True
    return False


def next_action_after_gate(verdict: Verdict, url: str) -> Action | None:
    """Map a gate verdict + URL to a follow-up action. None = no-op."""
    if verdict is Verdict.paywall or verdict is Verdict.block_page_detected:
        return RetryViaArchive(url=url)
    return None


def next_action_after_tier(tier_result: TierResult, url: str) -> Action | None:
    """Map a tier result + URL to a follow-up action. None = no-op."""
    # Rule 1: arxiv PDF → abs page rewrite (fires regardless of verdict)
    arxiv_match = _ARXIV_PDF_RE.match(url)
    if arxiv_match:
        arxiv_id = arxiv_match.group(1)
        return RewriteUrl(new_url=f"https://arxiv.org/abs/{arxiv_id}")

    # Rule 2: Cloudflare 403/429 → archive
    if tier_result.status_code in (403, 429) and _is_cloudflare(tier_result):
        return RetryViaArchive(url=url)

    return None


__all__ = [
    "Action",
    "RetryViaArchive",
    "RewriteUrl",
    "Skip",
    "next_action_after_gate",
    "next_action_after_tier",
]
