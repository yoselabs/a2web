"""Adaptive duration formatter — units match magnitude, no wasted precision.

`fmt_dur(ms)` is the only place duration strings are produced anywhere in
a2web. Hand-formatting durations elsewhere violates the response-format
spec.
"""

from __future__ import annotations


def fmt_dur(ms: int) -> str:
    """Format `ms` (integer milliseconds) per the four-tier rule.

    - `< 1000` → `"{ms}ms"` (integer, never `"0.0s"` for zero)
    - `1000 ≤ ms < 7000` → `"{s:.1f}s"` (one decimal)
    - `7000 ≤ ms < 60_000` → `"{s}s"` (integer)
    - `≥ 60_000` → `"{m}m{s:02d}s"`
    """
    if ms < 1000:
        return f"{ms}ms"
    if ms < 7000:
        return f"{ms / 1000:.1f}s"
    if ms < 60_000:
        return f"{ms // 1000}s"
    minutes, sec = divmod(ms // 1000, 60)
    return f"{minutes}m{sec:02d}s"
