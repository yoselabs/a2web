"""HTML → markdown extraction + metadata parsing — in-tree microsofware.

Trafilatura wrapper (sync, blocking — exposed via an async chokepoint
that punts to `asyncio.to_thread`) + OG/Twitter/JSON-LD metadata
extractor. Zero `a2web.<domain>` imports.

Boundary types (`ExtractedHeading`, `ExtractedLink`, `ExtractedContent`)
are package-owned dataclasses. The a2web seam (`extract/trafilatura_ext.py`)
maps them to the pydantic `Heading`/`Link` models used in the response
envelope.
"""

from __future__ import annotations

from .metadata import parse_metadata
from .trafilatura_ext import (
    ExtractedContent,
    ExtractedHeading,
    ExtractedLink,
    extract_markdown,
)

__all__ = (
    "ExtractedContent",
    "ExtractedHeading",
    "ExtractedLink",
    "extract_markdown",
    "parse_metadata",
)
