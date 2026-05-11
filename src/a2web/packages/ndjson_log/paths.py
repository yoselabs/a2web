"""Log path resolution. Pure functions, no side effects."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path


def log_dir() -> Path:
    """Resolve the log directory: `$A2WEB_LOG_DIR` if set, else `~/.a2web/logs/`."""
    override = os.environ.get("A2WEB_LOG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".a2web" / "logs"


def active_log_path(now: datetime | None = None) -> Path:
    """Path of the active NDJSON log for the given (or current) date."""
    moment = now or datetime.now(UTC)
    return log_dir() / f"fetches-{moment:%Y-%m-%d}.ndjson"
