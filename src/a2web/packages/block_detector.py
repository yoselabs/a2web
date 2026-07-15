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

# A raw body whose VISIBLE text (script/style/tags stripped, whitespace
# collapsed) is below this is "blank" — an essentially empty document, not
# merely a short page. Near-zero on purpose: `<html></html>` / an empty shell
# matches, but a ~480-char stub carrying a real sentence ("JavaScript is
# disabled…", >32 visible chars) does not. Distinct from `LENGTH_FLOOR`, which
# gates the EXTRACTED `content_md`; this gates the RAW body's own emptiness.
BLANK_HTML_THRESHOLD = 32

_SCRIPT_STYLE_BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# A page carrying JSON-LD structured data is NOT blank — its answer lives in the
# markup even when visible text is near-zero (a bare LocalBusiness/Product card).
# Such pages fall to `length_floor` and the structured-answer exemption, never
# `blank_page`, so a machine-readable answer is not mistaken for an empty shell.
_LD_JSON_RE = re.compile(r"""type\s*=\s*["']application/ld\+json""", re.IGNORECASE)


def _visible_text_len(raw_html: str) -> int:
    """Length of the raw body's visible text: drop <script>/<style> blocks and
    all tags, collapse whitespace. Used to detect an essentially-empty document
    (a silent-block empty shell) independently of trafilatura extraction."""
    stripped = _SCRIPT_STYLE_BLOCK_RE.sub(" ", raw_html)
    stripped = _TAG_RE.sub(" ", stripped)
    return len(_WS_RE.sub(" ", stripped).strip())


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
    blank_page = "blank_page"
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
    # Reddit's rate-limit / block interstitial ("whoa there, pardner!"). A real
    # wall with content behind it — catalogued so a thin rendered block body is
    # `block_page_detected` (a hard wall, loud `try_user_browser`), NOT laundered
    # into a bare `length_floor` that the thin-not-wall terminal would hedge as an
    # empty result. Companion to thin-not-wall: strengthen wall detection so only
    # genuinely evidence-free thinness downgrades.
    re.compile(r"whoa there,? pardner", re.IGNORECASE),
    re.compile(r"attempting to access a blocked page", re.IGNORECASE),
    # Bounded bespoke walls that otherwise fall through to a bare `length_floor`
    # and would be hedged as thin/empty. The wall space converges on a small set
    # of mitigation vendors (unlike the open-ended empty-result phrasing space),
    # so cataloguing these is maintainable and high-precision:
    #   - PerimeterX / HUMAN "Pardon the interruption" interstitial;
    #   - Incapsula/Imperva "Request unsuccessful. Incapsula incident ID" block.
    re.compile(r"pardon the interruption", re.IGNORECASE),
    re.compile(r"Request unsuccessful\.\s*Incapsula", re.IGNORECASE),
)

# Empty-result phrases — a CONSERVATIVE, high-precision multilingual set. This is
# a HINT, never an authority: a match only annotates a bare `length_floor` with
# `subsystem="empty_result"`, which (a) sharpens the terminal wording to
# `empty_unverified` and (b) is ONE necessary term in the promotion conjunction
# (`is_confirmed_empty`). It NEVER promotes to `ok` alone and NEVER suppresses a
# wall verdict (the branch runs AFTER every wall/JS-shell/blank branch). The empty
# space does not converge (millions of sites, every language), so this is NOT
# grown into a wall-style authority — the conjunction is what makes it safe.
_EMPTY_RESULT_PATTERNS = (
    re.compile(r"\bno results?\b", re.IGNORECASE),
    re.compile(r"\bno matches?\b", re.IGNORECASE),
    re.compile(r"\b0 results?\b", re.IGNORECASE),
    re.compile(r"\bno products?\s+(found|matched|available)\b", re.IGNORECASE),
    re.compile(r"\bnothing found\b", re.IGNORECASE),
    re.compile(r"\bdid not match any\b", re.IGNORECASE),
    re.compile(r"\byour search\b.{0,60}\b(returned no|found no|did not|matched no)\b", re.IGNORECASE | re.DOTALL),
    re.compile("bulunamadı", re.IGNORECASE),  # noqa: RUF001 — Turkish "was not found" (dotless-i), covers "sonuc bulunamad..."
)


def _matches_empty_result(content_md: str, raw_html: str) -> bool:
    """True when the visible body reads as an empty result set. Scans the extracted
    `content_md` first (the text the agent would read), then `raw_html` as a
    fallback for phrases trafilatura may have stripped."""
    return any(p.search(content_md) or p.search(raw_html) for p in _EMPTY_RESULT_PATTERNS)


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


# SPA mount points — the framework root divs and hydration-state globals that
# indicate a client-rendered app. Deliberately TIGHTER than
# `_JS_SHELL_ROOT_MARKERS` (which the length-gated js_required branch uses): it
# excludes `<noscript>`, web-component tags, and the Reddit anti-bot fields —
# all of which appear on plain static pages (analytics `<noscript>`, custom
# elements) and would false-positive the render-worthiness check.
_SPA_MOUNT_MARKERS = re.compile(
    r'id="__next"'
    r'|id="__nuxt"'
    r'|id="root"'
    r'|id="app"'
    r'|id="react-root"'
    r"|data-reactroot"
    r"|__NEXT_DATA__"
    r"|__NUXT_DATA__"
    r"|window\.__INITIAL_STATE__"
    r"|window\.__APOLLO_STATE__",
    re.IGNORECASE,
)


def looks_like_unrendered_spa(raw_html: str) -> bool:
    """True when the HTML shows client-side-rendering markers — a framework root
    mount (`id="root"` / `id="__next"` / hydration-state global) plus `<script>`
    tags.

    Length-independent, unlike the `js_required` branch in `evaluate` (which
    only fires below the length floor): a FAT SPA shell that passed the length
    floor still reads as unrendered here. Used to gate the obstacle-driven
    render — a plain static page that simply lacks the answer (a spec doc, a
    book) has no SPA mount, so re-rendering it would be pure cost. The mount set
    is intentionally strict: `<noscript>` / analytics scripts / custom elements
    on an otherwise-static page must NOT read as an unrendered SPA.
    """
    return bool(_SCRIPT_TAG_RE.search(raw_html) and _SPA_MOUNT_MARKERS.search(raw_html))


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

    # Blank page: the raw body itself carries near-zero visible text (an empty
    # shell, a WAF serving nothing to non-browser clients) — a distinct, higher-
    # precision signal than extracted-thin `length_floor`. Checked AFTER every
    # marker/JS-shell branch so a fingerprinted shell keeps its specific verdict;
    # this is the marker-less near-empty fallthrough. Escalates to browser (a
    # JS-rendered page can fill an empty shell); the orchestrator carries a still-
    # blank result to the paid scraper, then the loud blank_page terminal.
    if len(content_md) < LENGTH_FLOOR and _visible_text_len(raw_html) < BLANK_HTML_THRESHOLD and not _LD_JSON_RE.search(raw_html):
        return BlockResult(
            BlockVerdict.blank_page,
            escalation=EscalationSignal(next_tier="browser", reason="blank_page"),
        )

    if len(content_md) < LENGTH_FLOOR:
        # Empty-result annotation — LAST, after every wall/JS-shell/blank branch, so
        # a walled body that merely contains "no results" text keeps its wall
        # verdict. The marker only tags the bare fallthrough; it carries no
        # escalation and no `ok` promotion (that is the orchestrator's conjunction).
        if _matches_empty_result(content_md, raw_html):
            return BlockResult(BlockVerdict.length_floor, subsystem="empty_result")
        return BlockResult(BlockVerdict.length_floor)

    return BlockResult(BlockVerdict.ok)
