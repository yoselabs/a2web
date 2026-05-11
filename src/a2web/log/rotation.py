"""a2web seam — re-exports from `packages.ndjson_log`."""

from __future__ import annotations

from ..packages.ndjson_log import DEFAULT_ROTATION_BYTES, gzip_file, next_rolled_path

__all__ = ("DEFAULT_ROTATION_BYTES", "gzip_file", "next_rolled_path")
