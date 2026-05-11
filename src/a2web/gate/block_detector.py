"""Quality gate — a2web seam over `packages.block_detector`.

The detection logic lives in `a2web.packages.block_detector` as an
in-tree microsofware (no `a2web.<domain>` imports). This module is the
adapter at the a2web seam: it imports the package, calls it, and maps
the package's boundary types (`BlockVerdict`, `BlockResult`) onto the
wider `a2web.models.Verdict` enum used across the pipeline.

Block verdicts MUST cause the orchestrator to skip the cache write —
see `fetcher.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Verdict
from ..packages.block_detector import LENGTH_FLOOR as _LENGTH_FLOOR
from ..packages.block_detector import evaluate as _package_evaluate

LENGTH_FLOOR = _LENGTH_FLOOR


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

    Thin adapter over `packages.block_detector.evaluate`: forwards the
    inputs, maps `BlockVerdict → Verdict` (values are identical), and
    re-wraps in `GateResult` for the pipeline.
    """
    result = _package_evaluate(
        content_md=content_md,
        raw_html=raw_html,
        content_type=content_type,
    )
    return GateResult(
        verdict=Verdict(result.verdict.value),
        subsystem=result.subsystem,
        suggested_tier=result.suggested_tier,
    )
