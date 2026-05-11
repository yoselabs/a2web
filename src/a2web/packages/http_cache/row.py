"""Cache row boundary type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CacheRow:
    url: str
    profile_hash: str
    etag: str | None
    last_modified: str | None
    fetched_at: int
    expires_at: int
    status_code: int
    content_type: str | None
    content_hash: str
    body: bytes
