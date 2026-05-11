"""Quality gate — closed-enum verdicts on extracted content + headers.

Pure functions, no I/O. Run after extraction, before cache write. Block
verdicts MUST cause the orchestrator to skip the cache write — see
`fetcher.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Verdict

LENGTH_FLOOR = 500

# Tight markers — false positives on legitimate articles would be a real
# regression. Each one comes from observed block pages on real sites; do
# not weaken without an incident.
_BLOCK_PATTERNS = (
    re.compile(r"\bJust a moment\b", re.IGNORECASE),
    re.compile(r"\bcf-chl-bypass\b"),
    re.compile(r"\bAttention Required\b", re.IGNORECASE),
    re.compile(r"\bEnable JavaScript and cookies to continue\b", re.IGNORECASE),
    re.compile(r"\bAccess denied\b", re.IGNORECASE),
    re.compile(r"\bAre you a robot\b", re.IGNORECASE),
    re.compile(r"_Incapsula_"),
    re.compile(r"\bpx-captcha\b"),
    re.compile(r"\bYou've been blocked\b", re.IGNORECASE),
    re.compile(r"\bnetwork security\b", re.IGNORECASE),
)

_ANUBIS_MARKER = re.compile(r"anubis", re.IGNORECASE)

# Anti-bot system fingerprints → suggested escalation tier.
# Mappings come from engineering.md §2; conservative, only updated with cause.
_TURNSTILE_MARKER = re.compile(r"cf-turnstile|turnstile-callback|challenges\.cloudflare\.com/turnstile", re.IGNORECASE)
_AKAMAI_BMP_MARKER = re.compile(r"_abck=|bm_sz=|akam/\d+/[0-9a-f]{6,}", re.IGNORECASE)
_CF_INTERSTITIAL_MARKER = re.compile(r"\bcf-chl-bypass\b|\bJust a moment\b", re.IGNORECASE)
_NOSCRIPT_SHELL_MARKER = re.compile(r"<noscript>[^<]*(?:enable JavaScript|requires JavaScript)", re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<script\b", re.IGNORECASE)


@dataclass(slots=True)
class GateResult:
    verdict: Verdict
    subsystem: str | None = None
    suggested_tier: str | None = None


def evaluate(
    *,
    content_md: str,
    raw_html: str,
    content_type: str | None,
) -> GateResult:
    """Decide whether `content_md` is acceptable cache material.

    `content_md` is what the agent will read; `raw_html` is the unextracted
    body (used for marker scans that would be lost after extraction);
    `content_type` is the response header.
    """
    if content_type and "html" not in content_type.lower():
        # PR3 only handles HTML. Non-HTML responses (PDF, JSON) should not
        # have reached the gate — surface as content_type_mismatch so the
        # caller can decide whether to escalate.
        return GateResult(Verdict.content_type_mismatch)

    # Specific anti-bot families first — they carry suggested_tier hints
    # the orchestrator uses to smart-skip intermediate tiers.
    if _TURNSTILE_MARKER.search(raw_html):
        return GateResult(Verdict.anti_bot, subsystem="turnstile", suggested_tier="browser")
    if _AKAMAI_BMP_MARKER.search(raw_html):
        return GateResult(Verdict.anti_bot, subsystem="akamai_bmp", suggested_tier="browser")
    if _ANUBIS_MARKER.search(raw_html) and len(content_md) < LENGTH_FLOOR:
        return GateResult(Verdict.anti_bot, subsystem="anubis", suggested_tier="browser")

    if _CF_INTERSTITIAL_MARKER.search(raw_html):
        return GateResult(Verdict.block_page_detected, subsystem="cf_iuam", suggested_tier="tls_impersonate")

    for pattern in _BLOCK_PATTERNS:
        if pattern.search(raw_html):
            return GateResult(Verdict.block_page_detected)

    if _NOSCRIPT_SHELL_MARKER.search(raw_html) and len(content_md) < LENGTH_FLOOR and len(_SCRIPT_TAG_RE.findall(raw_html)) >= 3:
        return GateResult(Verdict.length_floor, subsystem="js_required", suggested_tier="browser")

    if len(content_md) < LENGTH_FLOOR:
        return GateResult(Verdict.length_floor)

    return GateResult(Verdict.ok)
