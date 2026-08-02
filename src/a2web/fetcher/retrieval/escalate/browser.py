"""The browser rung — fast Chromium, then robust CDP."""

from __future__ import annotations

import time

from any_browser import BrowserBackend

from .... import log as a2web_log
from ....decision_log import ObservationKind
from ....events.types import CorrelatedWitnessRung
from ....models import Diagnostic, Verdict
from ....state import AppState, ResourceUnavailable
from ....tiers import REGISTRY
from ...context import FetchContext, _within_budget
from ...retrieval.install import TierInstall, install
from ...telemetry import _emit_tier_ended, _emit_tier_started, _host


async def _escalate_browser(fc: FetchContext, *, state: AppState, scroll: bool = False) -> bool:
    """Dispatch a browser rung out-of-band; install its result on success.

    Returns whether content was installed. It does NOT comprehend what it
    installed — that is `escalate`'s job, and the split is the whole point: an
    escalator that calls comprehension forward is an escalator that can call
    PART of it, which is how the archive path came to run neither the ladder nor
    the sufficiency check. Private by convention; call `escalate`.

    `scroll` (listing-completeness Slice 2b) asks the browser to scroll the page
    to stable before snapshotting — the free own-browser listing-completion path.

    Two-rung fast→robust ladder on the SAME out-of-band dispatch: the rung is
    selected from `fc.browser_dispatches` — the first dispatch is the fast
    Chromium rung (`browser`, `fc.browser_backend`), the second the robust CDP
    rung (`browser_robust`, `fc.browser_robust_backend`). The playbook's browser
    rule (cap `< 2`) re-fires only when the fast render came back thin/blocked
    (gate still wants browser), so the robust rung never runs after a good fast
    render. Resolves the rung's `Lazy[...]` at this single seam — the engine only
    enters when its rung actually fires. A missing backend (caller didn't
    provision) surfaces `ResourceUnavailable`; we pass `backend=None` and the
    real `BrowserTier` short-circuits to an unavailable verdict.
    """
    is_robust = fc.browser_dispatches >= 1
    rung = "browser_robust" if is_robust else "browser"
    engine = state.settings.browser_backend_robust if is_robust else state.settings.browser_backend
    # Correlated-witness detection (fix-zendriver-robust-rung §3): the robust rung
    # is supposed to be a DISTINCT engine from the fast rung so a second escalation
    # is an independent second witness (load-bearing for classify_terminal's >=2
    # agreement + is_confirmed_empty). When it resolves to the same engine (the
    # homelab workaround pointing browser_robust at patchright while zendriver is
    # dead), the render is a same-engine retry, not independence — emit a WARNING so
    # the degradation is a detectable revert trigger, not institutional memory.
    correlated_witness = is_robust and state.settings.browser_backend_robust == state.settings.browser_backend
    if correlated_witness:
        await a2web_log.warning(
            CorrelatedWitnessRung(
                t_ms=int((time.perf_counter() - fc.start_perf) * 1000),
                engine=engine,
                host=_host(fc.final_url),
            ),
        )
    backend: BrowserBackend | None
    try:
        backend = await (fc.browser_robust_backend() if is_robust else fc.browser_backend())
    except ResourceUnavailable:
        backend = None
    browser_tier = REGISTRY[rung]
    br_start_ms = await _emit_tier_started(step=rung, host=_host(fc.final_url), start_perf=fc.start_perf)
    async with _within_budget(fc, about_to="tier:browser"):
        browser_result = await browser_tier.fetch(fc.final_url, state=state, backend=backend, scroll=scroll)
    fc.browser_dispatches += 1
    br_dur_ms = await _emit_tier_ended(
        step=rung,
        engine=engine,
        verdict=browser_result.verdict,
        start_ms=br_start_ms,
        start_perf=fc.start_perf,
        extra={"status_code": browser_result.status_code},
    )
    fc.diagnostics.append(
        Diagnostic(
            t_ms=br_start_ms,
            step=rung,
            engine=engine,
            host=_host(fc.final_url),
            proxy=None,
            verdict=browser_result.verdict,
            dur_ms=br_dur_ms,
            extra=(
                {"status_code": browser_result.status_code, "correlated_witness": engine}
                if correlated_witness
                else {"status_code": browser_result.status_code}
            ),
        )
    )
    # Record subresource-block evidence (a page XHR/fetch challenged during render)
    # ONLY when positive — the walled-API fake-empty signal. Recorded on a browser
    # tier_outcome so `classify_terminal` reads it as hard-wall evidence even when
    # the rendered shell body is a benign "0 results". Gated on `> 0` so a normal
    # render appends nothing new (zero perturbation to verdict resolution).
    if browser_result.subresource_blocks > 0:
        fc.observe(
            kind=ObservationKind.tier_outcome,
            source=rung,
            verdict=browser_result.verdict,
            status_code=browser_result.status_code,
            subresource_blocks=browser_result.subresource_blocks,
        )
    browser_pre = browser_result.pre_rendered
    if browser_result.verdict == Verdict.ok and browser_pre is not None:
        install(
            fc,
            TierInstall(
                body=browser_result.body,
                content_type=browser_result.content_type,
                final_url=browser_result.final_url,
                tier_used=rung,
                status_code=browser_result.status_code,
                pre_rendered=browser_pre,
                post_extract=True,
            ),
        )
        return True

    # The browser produced no usable content. If it rendered a real UPSTREAM
    # error page (a 404/paywall status surfaced by the tier), record it as an
    # observation so `classify_terminal` can corroborate a genuinely-gone URL.
    # A browser that merely failed to RUN (unavailable/timeout/internal error)
    # is not evidence about the target — it only surfaces its hint, no observation.
    if browser_result.verdict in (Verdict.not_found, Verdict.paywall):
        fc.observe(
            kind=ObservationKind.tier_outcome,
            source=rung,
            verdict=browser_result.verdict,
            status_code=browser_result.status_code,
        )
    if browser_result.operator_hint is not None:
        fc.operator_hints.append(browser_result.operator_hint)
    return False
