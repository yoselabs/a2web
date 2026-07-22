"""a2web — adaptive web fetching MCP server and CLI for AI agents."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version

try:
    # The single source of truth is `pyproject.toml`'s `version`. A hardcoded
    # constant here silently rots: it sat at `0.1.0.dev0` through 47 releases,
    # and the sunset put it on the wire (`a2web version`, `GET /health`), so a
    # deployed container would have reported a version that never shipped.
    __version__ = _installed_version("a2web")
except PackageNotFoundError:  # pragma: no cover — running from an uninstalled tree
    __version__ = "0.0.0.dev0"
