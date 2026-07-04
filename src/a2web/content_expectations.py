"""Content-readiness expectations — the oracle-vs-progress contract (`reddit-via-zyte`).

A **content expectation** declares an authoritative expected quantity (the
*oracle*) and a measured *progress* quantity, and resolves a fetched page to
`ready`, `partial`, or `fail`. It never treats a page as complete unless
progress meets the oracle within a declared tolerance. This is the
never-silently-miss tenet (ADR-0009) applied at content-item granularity: a
short-of-oracle read must surface an honest partial signal rather than pass as
a complete answer.

General seam, Reddit-first instance: the oracle is a thread's authoritative
comment total (`a.comments` bylink), progress is the number of parsed comments.
Pure — no I/O, no settings. Rungs that can *act* to increase progress (a future
browser rung scrolling/paginating) drive a bounded action loop off this
verdict; the Zyte/old.reddit path (server-rendered, one load) uses it as a pure
post-fetch assertion.
"""

from __future__ import annotations

from typing import Literal

Readiness = Literal["ready", "partial", "fail"]

# Completeness is measured against the FULL oracle (`total`), not the per-load
# ceiling: a 458-of-32,346 read is a sample the caller must be told about, even
# though 458 is all a single old.reddit load returns. That "we hit the ceiling"
# nuance rides in the partial *message* ("top-N of M"), not in the verdict.
# `TOLERANCE` absorbs trivial gaps (a handful of deleted/removed comments the
# oracle counts but that never render) so near-complete threads stay `ready`.
DEFAULT_TOLERANCE = 0.9


def assess(*, loaded: int, total: int | None, tolerance: float = DEFAULT_TOLERANCE) -> Readiness:
    """Resolve loaded-vs-oracle to `ready` / `partial` / `fail`.

    - No oracle (`total is None`) → `ready`: the site declares no expectation
      for this shape, so default readiness applies (no partial signal).
    - Oracle positive but nothing loaded (`total > 0 and loaded == 0`) → `fail`:
      the never-silently-miss case — comments provably exist yet none were
      retrieved; the caller must not present this as a complete answer.
    - Loaded meets the oracle within tolerance → `ready`.
    - Otherwise → `partial`: a labeled top-N-of-M sample, gap surfaced.
    """
    if total is None:
        return "ready"
    if total > 0 and loaded == 0:
        return "fail"
    return "ready" if loaded >= total * tolerance else "partial"


__all__ = ["DEFAULT_TOLERANCE", "Readiness", "assess"]
