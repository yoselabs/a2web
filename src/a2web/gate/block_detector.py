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

# v0.3: broader JS-shell root markers. A page with one of these AND a `<script>`
# tag AND below the length floor is a JS-rendered page where the raw HTML alone
# yielded ~no content. Browser tier is the right escalation.
# Patterns intentionally narrow: false positive surface = "framework root id +
# script + truly thin content" — that page benefits from browser regardless.
_JS_SHELL_ROOT_MARKERS = re.compile(
    r'id="__next"'  # Next.js
    r'|id="root"'  # React (CRA / Vite default)
    r'|id="app"'  # Vue / generic SPA
    r'|id="react-root"'  # Twitter / X
    r"|window\.__data__"  # Ember-style hydration
    r"|window\.__INITIAL_STATE__"  # common Redux SSR
    r"|<noscript",  # ANY noscript tag (progressive-enhancement signal)
    re.IGNORECASE,
)


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

    # v0.3 Linear-style FP fix: an interstitial / block-page marker on a page
    # that yielded substantive extracted content is NOT a block — sites embed
    # these phrases in security pages, cookie banners, compliance copy. Same
    # length-gated rule Anubis uses. Block pages by definition render no body.
    if len(content_md) < LENGTH_FLOOR:
        if _CF_INTERSTITIAL_MARKER.search(raw_html):
            return GateResult(Verdict.block_page_detected, subsystem="cf_iuam", suggested_tier="tls_impersonate")

        for pattern in _BLOCK_PATTERNS:
            if pattern.search(raw_html):
                return GateResult(Verdict.block_page_detected)

    # v0.3: thin extracted content + JS-shell signals → escalate to browser.
    # The narrower _NOSCRIPT_SHELL_MARKER variant (needs explicit "enable
    # JavaScript" text) misses most real SPAs. The broader rule catches
    # Next.js / React / Vue / Twitter / Ember roots — any one is enough when
    # combined with thin extracted content + at least one script tag.
    if len(content_md) < LENGTH_FLOOR and _SCRIPT_TAG_RE.search(raw_html) and _JS_SHELL_ROOT_MARKERS.search(raw_html):
        return GateResult(Verdict.length_floor, subsystem="js_required", suggested_tier="browser")

    if len(content_md) < LENGTH_FLOOR:
        return GateResult(Verdict.length_floor)

    return GateResult(Verdict.ok)
