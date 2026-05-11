"""a2web seam — re-exports `parse_metadata` from `packages.content_extract`."""

from __future__ import annotations

from ..packages.content_extract.metadata import parse_metadata

__all__ = ("parse_metadata",)
