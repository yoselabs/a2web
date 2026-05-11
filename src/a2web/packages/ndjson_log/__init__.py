"""NDJSON request log — in-tree microsofware.

Append-only NDJSON writer with lazy-open + size-based rotation + gzip on
rollover. Zero a2web-domain imports. The record shape (`LogRecord`) is
the boundary type; domain-specific construction (e.g. from a
`FetchResponse`) lives at the a2web seam in `a2web.log`.
"""

from __future__ import annotations

from .paths import active_log_path, log_dir
from .record import LogRecord, dominant_verdict
from .rotation import DEFAULT_ROTATION_BYTES, gzip_file, next_rolled_path
from .writer import LogWriter

__all__ = (
    "DEFAULT_ROTATION_BYTES",
    "LogRecord",
    "LogWriter",
    "active_log_path",
    "dominant_verdict",
    "gzip_file",
    "log_dir",
    "next_rolled_path",
)
