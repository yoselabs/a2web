"""Cache path resolution. Pure functions, no side effects."""

from __future__ import annotations

import os
from pathlib import Path


def cache_dir() -> Path:
    """Resolve the cache directory, honoring `$A2WEB_CACHE_DIR`."""
    override = os.environ.get("A2WEB_CACHE_DIR")
    return Path(override).expanduser() if override else Path.home() / ".a2web"
