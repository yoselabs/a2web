"""record_extract rendering — depth-aware markdown for a located region.

Pure string formatting. This module MUST NOT import from `a2web.<domain>`.
"""

from __future__ import annotations

# A record's own-scope text is truncated to this many chars in the render.
_MAX_RECORD_CHARS = 500
# Links rendered per record — the line is bounded, but no link is dropped
# from `Record.links` itself.
_MAX_LINKS_PER_RECORD = 10
# Junk that often sits between a heading title and the rest of the smush —
# stripped when peeling the heading off the body line so we don't surface
# orphan punctuation.
_BODY_LEAD_TRIM = " \t\xa0:|·,.-—"


def render_record(
    text: str,
    links: tuple[tuple[str, str], ...],
    depth: int,
    *,
    heading_text: str | None = None,
    heading_link: tuple[str, str] | None = None,
) -> str:
    """Render one record to a markdown list entry, indented by nesting depth.

    Structure (when a heading is present):

        - [heading_text](heading_link.href)
          {body — own-scope text with the heading_text peeled off the front}
          {remaining links — links minus the heading_link, ` · ` separated}

    A flat record (depth 0) renders flush-left; a threaded reply (depth > 0)
    is indented two spaces per level so the conversation shape survives.
    When no heading was detected, the render falls back to the legacy
    text-led row so non-aggregator listings still produce useful output.
    """
    indent = "  " * depth

    if heading_text is None:
        # Legacy text-led row — no heading detected.
        line = f"{indent}- {text[:_MAX_RECORD_CHARS]}"
        if links:
            rendered = " · ".join(f"[{anchor or href}]({href})" for anchor, href in links[:_MAX_LINKS_PER_RECORD])
            line += f"\n{indent}  {rendered}"
        return line

    # Heading-led row.
    lines: list[str] = []
    if heading_link is not None:
        _, href = heading_link
        lines.append(f"{indent}- [{heading_text}]({href})")
    else:
        lines.append(f"{indent}- {heading_text}")

    # Peel the heading_text off the body smush so it isn't duplicated. The
    # heading is usually near the front but action buttons / metadata can sit
    # before it (`Star…` on a GitHub card), so we strip the first occurrence
    # wherever it lands, then re-collapse the surrounding seam.
    body = text.replace(heading_text, " ", 1)
    body = " ".join(body.split())  # re-collapse whitespace after the peel
    body = body.strip(_BODY_LEAD_TRIM)
    body = body[:_MAX_RECORD_CHARS].strip()
    if body:
        lines.append(f"{indent}  {body}")

    # Remaining links — drop the heading_link's href to avoid duplication.
    heading_href = heading_link[1] if heading_link is not None else None
    remaining = [(a, h) for (a, h) in links if h != heading_href]
    if remaining:
        rendered = " · ".join(
            f"[{anchor or href}]({href})" for anchor, href in remaining[:_MAX_LINKS_PER_RECORD]
        )
        lines.append(f"{indent}  {rendered}")

    return "\n".join(lines)
