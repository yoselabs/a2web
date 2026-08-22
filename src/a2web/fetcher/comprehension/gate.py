"""The quality gate: is what we retrieved actually the page?"""

from __future__ import annotations

from dataclasses import dataclass as _dc

from ...decision_log import ObservationKind
from ...models import Verdict
from ...packages.block_detector import LENGTH_FLOOR, THIN_FALLTHROUGH
from ...packages.block_detector import evaluate as _package_evaluate
from ...packages.escalation import EscalationSignal
from ...settings import AppSettings
from ..context import FetchContext


@_dc(slots=True)
class _GateResult:
    """Domain-typed wrapper over `packages.block_detector.BlockResult`."""

    verdict: Verdict
    subsystem: str | None = None
    escalation: EscalationSignal | None = None
    # True when the structured-answer exemption is what flipped a bare
    # length_floor to ok — i.e. this ok is a thin page whose only answer source
    # was an answer-bearing structured candidate. Carried so the ask projection
    # can suppress a false `obstacle: empty` incompleteness flag
    # (structured-grounded-completeness).
    promoted_structured: bool = False


_THIN_BROWSER_MAX_BODY: int = 1_024

# Hosts known to be JS-heavy CSR apps. When the browser tier returns a thin
# 200 OK from one of these, the gate downgrades to length_floor so escalation
# continues (operator can extend via AppSettings.js_heavy_hosts_extra).
#
# `hepsiburada.com` is deliberately absent (a2web-cid) — not an oversight and
# not something to add on symmetry with trendyol.com/aliexpress.com alone.
# Evidence, both from before this seed existed:
#   - The 2026-05-19 harsh-test session that seeded this set (see
#     `openspec/changes/archive/2026-05-19-harsh-test-session-fixes/design.md`)
#     explicitly classified "Hepsiburada / Amazon.com.tr" as SSR e-commerce,
#     raw-tier win, in the same breath that classified Trendyol / Yandex
#     Market as CSR, partial-or-failed — i.e. hepsiburada was tested and
#     excluded, not overlooked. `_JS_HEAVY_HOSTS_SEED` was seeded from exactly
#     that split.
#   - `tests/fixtures/hepsiburada_listing.html` and the frozen regression case
#     `eval/corpus/regression/hepsiburada-listing-price` both show hepsiburada
#     product/listing pages ship their product data as `application/ld+json`
#     inside the raw HTML — the raw tier's own body carries the answer, so a
#     JS render recovers nothing raw doesn't already have.
# This branch (`tier == "browser"`) only fires once a fetch has already
# reached the browser tier and come back thin; it never governs whether raw
# escalates to browser in the first place (that's the generic block_detector
# verdict on the raw tier's own content, in `packages/block_detector.py`).
# One live counter-signal exists — `eval/findings_2026-06-27.md` found the
# hepsiburada *search* page (`/ara?q=...`, not a product page) needed the
# `zendriver` browser backend to read at all — but that page's fast-tier
# response was already empty (md_len=0), so it already trips the generic
# `LENGTH_FLOOR` (packages/block_detector.py) without needing host membership
# here. If a future thin-but-`ok` (500-1023 char) browser shell shows up on
# hepsiburada, that is new evidence and reopens this decision.
_JS_HEAVY_HOSTS_SEED: frozenset[str] = frozenset(
    {
        "x.com",
        "twitter.com",
        "instagram.com",
        "tiktok.com",
        "trendyol.com",
        "aliexpress.com",
    }
)


def js_heavy_hosts(settings: AppSettings | None = None) -> frozenset[str]:
    """Return the union of seed + settings-extra JS-heavy hosts."""
    if settings is None or not settings.js_heavy_hosts_extra:
        return _JS_HEAVY_HOSTS_SEED
    return _JS_HEAVY_HOSTS_SEED | frozenset(h.strip().lower() for h in settings.js_heavy_hosts_extra if h.strip())


def evaluate(
    *,
    content_md: str,
    raw_html: str,
    content_type: str | None,
    tier: str | None = None,
    host: str | None = None,
    settings: AppSettings | None = None,
    is_json: bool = False,
    structured_answer: bool = False,
) -> _GateResult:
    """Run the package's block detector, map BlockVerdict → Verdict.

    Reader-wrapper decoding (a jina 200 masking an upstream error) is NOT done
    here anymore — it is tier work (`tiers/jina.py` surfaces the real upstream
    status), so the gate no longer branches on `tier == "jina"`.
    """
    result = _package_evaluate(content_md=content_md, raw_html=raw_html, content_type=content_type)
    verdict = Verdict(result.verdict.value)
    subsystem = result.subsystem
    escalation = result.escalation

    if tier == "browser" and len(content_md) < _THIN_BROWSER_MAX_BODY and host and verdict in (Verdict.ok, Verdict.length_floor):
        norm_host = host.lower()
        if norm_host.startswith("www."):
            norm_host = norm_host[4:]
        host_matches = norm_host in js_heavy_hosts(settings)
    else:
        host_matches = False
    if host_matches:
        verdict = Verdict.length_floor
        subsystem = "thin_browser_response"

    # A small-but-complete JSON response (`{"count": 42}`) is a valid answer, not
    # a truncated SPA shell. Exempt JSON from the thin-shell length floor — keyed
    # STRICTLY on the JSON content-type, so HTML shells keep the full floor (the
    # v0.29.0 confabulation guard is untouched).
    if is_json and verdict in (Verdict.length_floor, Verdict.blank_page):
        verdict = Verdict.ok
        subsystem = None
        escalation = None

    # A thin page whose answer lives in answer-bearing structured data (a strong
    # JSON-LD LocalBusiness/Product/…) is small-but-complete, not a truncated
    # shell — mirror the `is_json` promotion. Scoped to the BARE length_floor
    # (`subsystem is None`): a `js_required` / `thin_browser_response` shell keeps
    # its subsystem here and continues escalating even if it embeds a stub
    # payload, so no wall is masked. The `structured_answer` flag is set by the
    # caller from `ContentCandidate.answer_bearing` (strong payloads only).
    promoted_structured = False
    if structured_answer and verdict is Verdict.length_floor and subsystem in (None, THIN_FALLTHROUGH):
        verdict = Verdict.ok
        subsystem = None
        promoted_structured = True

    # A length-independent anti-bot marker (akamai_bmp/turnstile) only means
    # "this site is bot-defended" — not "this specific response was blocked".
    # When the response is well above the length floor (a real page, not a
    # challenge shell) AND its answer already lives in an answer-bearing
    # structured candidate, forcing a browser escalation changes nothing but
    # cost. Scoped to exactly these two markers: anubis/alibaba_punish/cf_iuam
    # and generic block_page_detected are genuine thin-shell/interstitial
    # fingerprints and must keep escalating regardless of structured_answer.
    if structured_answer and verdict is Verdict.anti_bot and subsystem in ("akamai_bmp", "turnstile") and len(content_md) >= LENGTH_FLOOR:
        verdict = Verdict.ok
        subsystem = None
        escalation = None
        promoted_structured = True

    return _GateResult(verdict=verdict, subsystem=subsystem, escalation=escalation, promoted_structured=promoted_structured)


def _regate_after_escalation(fc: FetchContext) -> None:
    """Re-evaluate the gate on freshly-installed escalation content.

    Used after both browser and gate-path archive installs. Appends a
    gate-outcome observation to the decision log — the new observation IS
    the new gate state (no mutable snapshot to keep in sync). The
    pre-rendered markdown plays both the `content_md` and `raw_html`
    roles — the underlying body is no longer the discriminator at this
    point in the pipeline.
    """
    regate = evaluate(content_md=fc.content_md, raw_html=fc.content_md, content_type=None)
    subsystem = None if regate.verdict is Verdict.ok else regate.subsystem
    fc.observe(
        kind=ObservationKind.gate_outcome,
        source="regate",
        verdict=regate.verdict,
        # Carry the escalation signal so a still-blocked escalation result can
        # re-trigger the playbook — this is what lets the fast `browser` rung
        # escalate to `browser_robust` when its render is still thin/blocked
        # (the browser rule requires `escalation.next_tier == "browser"`).
        escalation=regate.escalation,
        subsystem=subsystem,
    )
