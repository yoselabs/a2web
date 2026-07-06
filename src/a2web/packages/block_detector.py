"""Block-page detector — in-tree microsofware (packages/).

Pure functions over `(content_md, raw_html, content_type)` returning a
closed-enum verdict + optional subsystem fingerprint + suggested
escalation tier. No I/O, no a2web-domain imports.

Boundary types (`BlockVerdict`, `BlockResult`) are owned by this package.
The a2web seam (`gate/block_detector.py`) adapts them to the wider
`a2web.models.Verdict` enum used across the pipeline.

Pattern catalogue rules:
- Tight markers — false positives on legitimate articles would be a
  real regression. Each comes from observed block pages on real sites;
  do not weaken without an incident.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .escalation import EscalationSignal

LENGTH_FLOOR = 500


class BlockVerdict(StrEnum):
    """Subset of verdicts this detector itself produces.

    Values intentionally match `a2web.models.Verdict` strings so the
    a2web seam can `Verdict(result.verdict.value)` without a lookup
    table. Other Verdict members (paywall, timeout, not_found, …) are
    produced elsewhere in the pipeline, not here.
    """

    ok = "ok"
    block_page_detected = "block_page_detected"
    anti_bot = "anti_bot"
    length_floor = "length_floor"
    content_type_mismatch = "content_type_mismatch"


@dataclass(slots=True, frozen=True)
class BlockResult:
    verdict: BlockVerdict
    subsystem: str | None = None
    # Typed escalation signal (Phase 4). The detector emits typed evidence —
    # the planner decides whether to act. `reason` mirrors `subsystem` for
    # the matching marker family ("js_required", "cf_iuam", "turnstile", ...).
    escalation: EscalationSignal | None = None


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
_TURNSTILE_MARKER = re.compile(r"cf-turnstile|turnstile-callback|challenges\.cloudflare\.com/turnstile", re.IGNORECASE)
_AKAMAI_BMP_MARKER = re.compile(r"_abck=|bm_sz=|akam/\d+/[0-9a-f]{6,}", re.IGNORECASE)
_CF_INTERSTITIAL_MARKER = re.compile(r"\bcf-chl-bypass\b|\bJust a moment\b", re.IGNORECASE)
_SCRIPT_TAG_RE = re.compile(r"<script\b", re.IGNORECASE)

# Alibaba Baxia "punish" anti-bot interstitial — the wall fronting AliExpress
# and other Alibaba-family sites. raw curl_cffi follows the redirect and lands
# on the punish page, whose body carries these markers (observed on real
# fetches: the `_____tmd_____` path token + `x5secdata`/`x5step` params, the
# AWSC slider widget ids, and the localized interstitial text). Markers are
# distinctive to the punish flow — matched length-independently (like
# turnstile/akamai) so a punish page surfaced by the browser tier on an
# already-flagged IP is caught too. Deliberately NOT matching bare "captcha"
# or the generic "unusual traffic" phrase (that one belongs to the Google/Bing
# search-captcha matcher below) to avoid false positives.
_ALIBABA_BAXIA_MARKER = re.compile(
    r"_____tmd_____"  # Baxia punish path / asset token
    r"|x5secdata|x5step"  # punish-flow query params
    r"|slidecaptcha|nocaptcha|nc_iconfont"  # AWSC slider widget ids/classes
    r"|\bbaxia\b"  # the anti-bot system name (cdn path / script)
    r"|slide to verify"  # aliexpress.com English interstitial phrase
    r"|Captcha Interception"  # aliexpress.com punish <title>
    r"|Пройдите проверку",  # aliexpress.ru Russian interstitial heading
    re.IGNORECASE,
)

# Search-engine captcha markers — second-line defense for captcha redirects
# that escape the upfront `rewrite_captcha_host` pre-routing in `domain.py`
# (e.g. an inbound Google redirect we don't recognize that lands on
# /sorry/index). The gate maps `subsystem="captcha_redirect"` to an
# OperatorHint pointing the caller at DDG/Brave.
_SEARCH_CAPTCHA_MARKER = re.compile(
    r"Our systems have detected unusual traffic"  # Google /sorry/index body
    r"|/sorry/index"  # /sorry path leaked into HTML/JS
    r"|We're sorry\.\.\."  # Google sorry-page heading
    r"|Bing/Block/CaptchaChallenge"  # Bing captcha intermediate
    r"|<title>Bing</title>.{0,400}captcha"  # Bing's captcha page title cluster
    r"|/fd/ls/lsp\.aspx",  # Bing block-page asset path
    re.IGNORECASE | re.DOTALL,
)

_JS_SHELL_ROOT_MARKERS = re.compile(
    r'id="__next"'
    r'|id="root"'
    r'|id="app"'
    r'|id="react-root"'
    r"|window\.__data__"
    r"|window\.__INITIAL_STATE__"
    r"|<noscript"
    # Reddit JS-challenge anti-bot interstitial: server returns a thin
    # body with a hidden form whose JS solves the challenge and resubmits
    # to get the real SPA. We never solve it in raw, so we need to
    # escalate to browser. Both fields are Reddit-specific (jsc = "JS
    # challenge"); generic `name="solution"` was deliberately excluded
    # to avoid false positives on legitimate quiz/exam sites.
    r'|name="js_challenge"'
    r'|name="jsc_orig_r"'
    # Generic web-component SPA shell. Per HTML Living Standard §4.13,
    # custom-element tag names MUST contain a hyphen and start with a
    # lowercase ASCII letter. Built-in HTML tags (<div>, <article>)
    # never have hyphens, so false positives on static HTML are
    # essentially zero (requires <-prefix; attribute values like
    # data-foo="x-y" do not match).
    r"|<[a-z][a-z0-9]*-[a-z][a-z0-9-]*",
    re.IGNORECASE,
)


def looks_like_unrendered_spa(raw_html: str) -> bool:
    """True when the HTML shows client-side-rendering markers — a root mount
    point (`id="root"` / `__next` / a web-component tag) plus `<script>` tags.

    Length-independent, unlike the `js_required` branch in `evaluate` (which
    only fires below the length floor): a FAT SPA shell that passed the length
    floor still reads as unrendered here. Used to gate the obstacle-driven
    render — a plain static page that simply lacks the answer (a spec doc, a
    book) has no such markers, so re-rendering it would be pure cost.
    """
    return bool(_SCRIPT_TAG_RE.search(raw_html) and _JS_SHELL_ROOT_MARKERS.search(raw_html))


def evaluate(
    *,
    content_md: str,
    raw_html: str,
    content_type: str | None,
) -> BlockResult:
    """Decide whether `content_md` is acceptable cache material.

    `content_md` is what the agent will read; `raw_html` is the
    unextracted body (used for marker scans that would be lost after
    extraction); `content_type` is the response header.
    """
    if content_type and "html" not in content_type.lower():
        return BlockResult(BlockVerdict.content_type_mismatch)

    if _TURNSTILE_MARKER.search(raw_html):
        return BlockResult(
            BlockVerdict.anti_bot,
            subsystem="turnstile",
            escalation=EscalationSignal(next_tier="browser", reason="turnstile"),
        )
    if _AKAMAI_BMP_MARKER.search(raw_html):
        return BlockResult(
            BlockVerdict.anti_bot,
            subsystem="akamai_bmp",
            escalation=EscalationSignal(next_tier="browser", reason="akamai_bmp"),
        )
    if _ANUBIS_MARKER.search(raw_html) and len(content_md) < LENGTH_FLOOR:
        return BlockResult(
            BlockVerdict.anti_bot,
            subsystem="anubis",
            escalation=EscalationSignal(next_tier="browser", reason="anubis"),
        )
    if _ALIBABA_BAXIA_MARKER.search(raw_html):
        return BlockResult(
            BlockVerdict.anti_bot,
            subsystem="alibaba_punish",
            escalation=EscalationSignal(next_tier="browser", reason="alibaba_punish"),
        )
    if _SEARCH_CAPTCHA_MARKER.search(raw_html):
        # Belt-and-suspenders for any Google/Bing redirect that escapes
        # `domain.rewrite_captcha_host`. Gate phase maps the subsystem
        # to an operator_hint pointing the caller at DDG.
        return BlockResult(BlockVerdict.block_page_detected, subsystem="captcha_redirect")

    if len(content_md) < LENGTH_FLOOR:
        if _CF_INTERSTITIAL_MARKER.search(raw_html):
            return BlockResult(
                BlockVerdict.block_page_detected,
                subsystem="cf_iuam",
                escalation=EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam"),
            )

        for pattern in _BLOCK_PATTERNS:
            if pattern.search(raw_html):
                return BlockResult(BlockVerdict.block_page_detected)

    if len(content_md) < LENGTH_FLOOR and _SCRIPT_TAG_RE.search(raw_html) and _JS_SHELL_ROOT_MARKERS.search(raw_html):
        return BlockResult(
            BlockVerdict.length_floor,
            subsystem="js_required",
            escalation=EscalationSignal(next_tier="browser", reason="js_required"),
        )

    if len(content_md) < LENGTH_FLOOR:
        return BlockResult(BlockVerdict.length_floor)

    return BlockResult(BlockVerdict.ok)
