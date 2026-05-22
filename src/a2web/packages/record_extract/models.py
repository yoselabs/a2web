"""record_extract boundary types — `Record` and `RecordSet`.

Pure dataclasses. This module MUST NOT import from `a2web.<domain>`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Record:
    """One extracted record from a listing or threaded discussion.

    `links` carries every own-scope link (anchor text, href) — own scope
    excludes links inside nested same-signature child-records, so an outer
    comment is not credited with its replies' links. `primary_link` is the
    record's identifying link — its heading link (the discussed page), or the
    longest-anchor fallback. `depth` is the record's nesting depth within the
    region: 0 for a flat catalog row, > 0 for a nested comment reply.
    """

    text: str
    links: tuple[tuple[str, str], ...]
    primary_link: tuple[str, str] | None
    depth: int
    markdown: str


@dataclass(slots=True, frozen=True)
class RecordSet:
    """The located dominant record region and its rendered records."""

    records: tuple[Record, ...]
    container: str
    child_signature: str
    max_depth: int

    @property
    def is_threaded(self) -> bool:
        """True when records nest — a threaded discussion, not a flat list."""
        return self.max_depth > 0

    def to_markdown(self) -> str:
        """Render the whole record set to a markdown block.

        Each record's `markdown` is already depth-indented, so the set render
        is a header plus the pre-rendered record lines.
        """
        label = "Discussion" if self.is_threaded else "Listing"
        noun = "comments" if self.is_threaded else "records"
        body = "\n".join(r.markdown for r in self.records)
        return f"### {label} ({len(self.records)} {noun})\n\n{body}"
