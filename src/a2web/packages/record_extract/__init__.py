"""record_extract — locate and extract repeated data records from HTML.

A listing / index / threaded-discussion page is N repeated records, not one
article. trafilatura discards that repeated structure as boilerplate; this
package recovers it: a tree-aware detector locates the dominant repeated
record region (`detector`), and a depth-aware renderer turns it into
link-preserving markdown (`render`). Boundary types live in `models`.

Public surface: `extract_records(html, base_url) -> RecordSet | None`.
"""

from __future__ import annotations

from .detector import extract_records
from .models import Record, RecordSet

__all__ = ("Record", "RecordSet", "extract_records")
