"""record_extract rendering — depth-aware markdown for a located region.

Pure string formatting. This module MUST NOT import from `a2web.<domain>`.
"""

from __future__ import annotations

# A record's own-scope text is truncated to this many chars in the render.
_MAX_RECORD_CHARS = 500
# Links rendered per record — the line is bounded, but no link is dropped
# from `Record.links` itself.
_MAX_LINKS_PER_RECORD = 10


def render_record(text: str, links: tuple[tuple[str, str], ...], depth: int) -> str:
    """Render one record to a markdown list entry, indented by nesting depth.

    A flat record (depth 0) renders flush-left; a threaded reply (depth > 0)
    is indented two spaces per level so the conversation shape survives. Every
    link is link-preserving — anchor text and href both kept.
    """
    indent = "  " * depth
    line = f"{indent}- {text[:_MAX_RECORD_CHARS]}"
    if links:
        rendered = " · ".join(f"[{anchor or href}]({href})" for anchor, href in links[:_MAX_LINKS_PER_RECORD])
        line += f"\n{indent}  {rendered}"
    return line
