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


@dataclass(slots=True)
class GateResult:
    verdict: Verdict
    subsystem: str | None = None


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

    for pattern in _BLOCK_PATTERNS:
        if pattern.search(raw_html):
            return GateResult(Verdict.block_page_detected)

    if _ANUBIS_MARKER.search(raw_html) and len(content_md) < LENGTH_FLOOR:
        return GateResult(Verdict.anti_bot, subsystem="anubis")

    if len(content_md) < LENGTH_FLOOR:
        return GateResult(Verdict.length_floor)

    return GateResult(Verdict.ok)
