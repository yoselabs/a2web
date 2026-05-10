"""Parse short duration strings like "1h", "30m", "7d" → timedelta.

Used by `a2web logs tail --since=...`. Strict-parse: integer + single
unit suffix; anything else raises ValueError.
"""

from __future__ import annotations

import re
from datetime import timedelta

_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)
_FACTORS = {
    "s": 1,
    "m": 60,
    "h": 3600,
    "d": 86400,
}


def parse_duration(text: str) -> timedelta:
    """Parse `<int><s|m|h|d>` (case-insensitive) into a `timedelta`.

    Examples: "30s", "15m", "1h", "7d". Raises ValueError on malformed input.
    """
    match = _RE.match(text)
    if match is None:
        raise ValueError(f"Invalid duration: {text!r}; expected e.g. '1h', '30m', '7d'")
    value = int(match.group(1))
    unit = match.group(2).lower()
    return timedelta(seconds=value * _FACTORS[unit])


__all__ = ["parse_duration"]
