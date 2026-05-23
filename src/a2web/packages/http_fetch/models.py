"""http_fetch boundary types — `FetchVerdict` + `FetchOutcome`.

This module MUST NOT import from `a2web.<domain>`. `FetchVerdict` is a
transport-layer subset of the project's domain `Verdict` enum — only the
values a pure HTTP primitive can determine. Tier / handler callers translate
to the domain `Verdict` (which adds policy verdicts like `paywall`,
`block_page_detected`, etc. that are not transport concerns).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FetchVerdict(StrEnum):
    """Transport-layer outcome of a single HTTP fetch."""

    ok = "ok"
    not_found = "not_found"
    rate_limited = "rate_limited"
    connection_error = "connection_error"
    timeout = "timeout"
    proxy_unavailable = "proxy_unavailable"


@dataclass(slots=True, frozen=True)
class FetchOutcome:
    """One HTTP fetch's result — bytes + closed verdict, never an exception.

    `final_url` is the URL after redirects. `conditional_hit` is True only
    for a 304 response served against `conditional_extras`; the body is
    empty and the caller is expected to reuse a cached body.
    """

    body: bytes
    content_type: str
    status_code: int
    final_url: str
    headers: dict[str, str] = field(default_factory=dict)
    verdict: FetchVerdict = FetchVerdict.ok
    conditional_hit: bool = False
