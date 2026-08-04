"""Archive dispatch, its two installs, and the post-gate rung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ....decision_log import ObservationKind
from ....models import Diagnostic, Verdict
from ....state import AppState
from ....tiers import REGISTRY, Rendered
from ...context import FetchContext
from ...retrieval.install import TierInstall, install
from ...telemetry import _emit_tier_ended, _emit_tier_started, _host

# --------------------------------------------------------------------- #
# Archive escalation helper (shared by after-tier + after-gate)
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class _ArchiveOutcome:
    """Result of one archive-tier dispatch — used by `_dispatch_archive`."""

    success: bool
    body: bytes = b""
    content_type: str = ""
    final_url: str = ""
    pre_rendered: Rendered | None = None
    status_code: int = 0
    #: Age of the winning snapshot. The archive tier has computed this since it
    #: was written and NOTHING carried it — see `archive_snapshot_age_hint`.
    snapshot_age_days: int | None = None
    #: The snapshot's calendar date — outlives the age, which decays on contact.
    snapshot_taken_at: date | None = None


async def _dispatch_archive(
    url: str,
    *,
    state: AppState,
    start_perf: float,
    diagnostics: list[Diagnostic],
) -> _ArchiveOutcome:
    """One-stop archive dispatch — used by both after-tier and after-gate paths.

    Emits TierStarted/TierEnded around the archive fetch, appends a Diagnostic
    ALWAYS, and returns an outcome the caller installs into orchestrator state.

    **Always, not only on success — changed 2026-08-03.** This appended a row
    only when the archive won, on the stated grounds that a failed escalation is
    "tried, didn't help" and "should not displace the originating verdict".
    That reason stopped being true and the prose survived: `resolve_verdict`
    reads `Observation`s, not `Diagnostic`s (`decision_log.py` filters on
    `ObservationKind`), and the verdict became a pure projection of the decision
    log in v0.23. A `Diagnostic` has no path into verdict resolution at all.

    What the silence cost is ADR-0009 visibility. The diagnostics list is where
    "what did you try" lives, so a failed archive dispatch left a gap exactly
    where an attempt had been — "we never tried the archive" and "we tried and
    it did not help" rendered identically to the caller. The cheap half of the
    ADR-0009 harm, but the same direction.

    Browser, paid and the tier loop have always appended unconditionally; this
    was the one divergence.
    """
    archive_tier = REGISTRY["archive"]
    arch_start_ms = await _emit_tier_started(step="archive", host=_host(url), start_perf=start_perf)
    archive_result = await archive_tier.fetch(url, state=state)
    engine = archive_result.archive_source or "archive"
    arch_dur_ms = await _emit_tier_ended(
        step="archive",
        engine=engine,
        verdict=archive_result.verdict,
        start_ms=arch_start_ms,
        start_perf=start_perf,
        extra={"status_code": archive_result.status_code},
    )
    # Appended BEFORE the success check: the row records the attempt, and an
    # attempt that failed is exactly the one a caller cannot otherwise see.
    diagnostics.append(
        Diagnostic(
            t_ms=arch_start_ms,
            step="archive",
            engine=engine,
            host=_host(url),
            proxy=None,
            verdict=archive_result.verdict,
            dur_ms=arch_dur_ms,
            extra={"status_code": archive_result.status_code},
        )
    )
    archive_pre = archive_result.pre_rendered
    if archive_result.verdict != Verdict.ok or archive_pre is None:
        return _ArchiveOutcome(success=False)
    return _ArchiveOutcome(
        success=True,
        body=archive_result.body,
        content_type=archive_result.content_type,
        final_url=archive_result.final_url,
        pre_rendered=archive_pre,
        status_code=archive_result.status_code,
        snapshot_age_days=archive_result.snapshot_age_days,
        snapshot_taken_at=archive_result.snapshot_taken_at,
    )


def _install_archive_payload(fc: FetchContext, outcome: _ArchiveOutcome) -> None:
    """Install a tier-loop archive escalation outcome onto FetchContext.

    Runs before `_phase_extract`, so it installs the body only — extraction
    fills `content_md` from `pre_rendered_payload`. Appends the archive's
    winning observation.
    """
    install(
        fc,
        TierInstall(
            body=outcome.body,
            content_type=outcome.content_type,
            final_url=outcome.final_url,
            tier_used="archive",
            status_code=outcome.status_code,
            pre_rendered=outcome.pre_rendered,
        ),
    )
    fc.snapshot_age_days = outcome.snapshot_age_days
    fc.snapshot_taken_at = outcome.snapshot_taken_at
    fc.observe(kind=ObservationKind.tier_outcome, source="archive", verdict=Verdict.ok)


def _install_gate_archive(fc: FetchContext, outcome: _ArchiveOutcome) -> None:
    """Install a gate-path archive escalation outcome onto FetchContext.

    Unlike `_install_archive_payload`, this lands after `_phase_extract` has
    run — so it sets the extracted fields directly from the archive's
    pre-rendered payload.
    """
    pre = outcome.pre_rendered
    assert pre is not None  # noqa: S101 — narrowed by the caller
    install(
        fc,
        TierInstall(
            body=outcome.body,
            content_type=outcome.content_type,
            final_url=outcome.final_url,
            tier_used="archive",
            # NOT set before the chokepoint existed, while the pre-gate sibling
            # above always set it. Inert today (`fc.status_code` has exactly one
            # reader, `_phase_cache_write`, which declines archive results
            # outright) — so this is a trap disarmed, not a behaviour change: the
            # path was one cacheable-archive decision away from writing a foreign
            # tier's status into the cache row.
            status_code=outcome.status_code,
            pre_rendered=pre,
            post_extract=True,
        ),
    )
    fc.snapshot_age_days = outcome.snapshot_age_days
    fc.snapshot_taken_at = outcome.snapshot_taken_at


async def _escalate_archive_post_gate(fc: FetchContext, *, state: AppState, scroll: bool = False) -> bool:
    """Archive, dispatched after the gate has already run.

    `scroll` is accepted and ignored — the archive serves a frozen snapshot, so
    there is nothing to scroll. It exists so every rung has one signature and
    `escalate` needs no per-rung special case.
    """
    del scroll
    fc.archive_dispatches += 1
    outcome = await _dispatch_archive(fc.final_url, state=state, start_perf=fc.inputs.start_perf, diagnostics=fc.diagnostics)
    if not (outcome.success and outcome.pre_rendered is not None):
        return False
    _install_gate_archive(fc, outcome)
    return True
