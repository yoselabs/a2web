"""Archive tier — hedged Wayback CDX + archive.ph fallback.

Out-of-band tier: registered but NOT in `TIER_ORDER`. The orchestrator
dispatches it only when the playbook returns `RetryViaArchive`.

Hedge strategy: launch both upstreams under an anyio task group, write to
a single capacity-1 send stream on first success, cancel the loser on
task-group exit. All HTTP goes through the shared `http_fetch` primitive —
no inline curl_cffi or httpx.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import anyio
from content_extract import ExtractedContent, extract_markdown
from http_fetch import FetchVerdict, fetch_bytes

from ..models import Heading, Link, Verdict


@dataclass(slots=True)
class _Winner:
    source: str
    html: str
    timestamp: str | None = None


if TYPE_CHECKING:
    from ..state import AppState
    from . import TierResult


_CDX_URL = "https://web.archive.org/cdx/search/cdx"
_WAYBACK_SNAPSHOT = "https://web.archive.org/web/{timestamp}id_/{url}"
_ARCHIVE_PH = "https://archive.ph/newest/{url}"
_TIMEOUT_S = 12.0

_WAYBACK_CHROME_RE = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT.*?<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_WAYBACK_DIV_RE = re.compile(r'<div id="wm-ipp-base".*?</div>', re.DOTALL | re.IGNORECASE)


def _strip_wayback_chrome(html: str) -> str:
    html = _WAYBACK_CHROME_RE.sub("", html)
    return _WAYBACK_DIV_RE.sub("", html)


async def _extract(html: str, url: str) -> ExtractedContent:
    """Canonical extraction — markdown AND links AND headings, one off-thread parse.

    NOT a bare `trafilatura.extract`; see `tiers/browser.py::_extract` and
    `tests/architecture/test_trafilatura_funnel.py` for why that call shape is
    banned. An archive snapshot is often the ONLY copy of a dead page, so losing
    its anchors here is the least recoverable version of the defect.

    `include_links` is deliberately NOT set. Measured 2026-07-28: the flag
    changes only how `content_md` RENDERS — the structured `links` list is
    returned either way — and turning it on destroys list structure (a 3-bullet
    listing rendered as 0 bullets with items run together). The digest needs the
    structured links; the model reads the markdown. Taking both from one
    default-flag parse costs nothing and keeps the body readable.
    """
    return await extract_markdown(html, url)


async def _wayback_lookup(url: str, *, timeout_s: float) -> tuple[str, str] | None:
    """Return (timestamp, snapshot_html) or None."""
    cdx_qs = urlencode({"url": url, "output": "json", "limit": 1, "fl": "timestamp,original"})
    cdx_outcome = await fetch_bytes(f"{_CDX_URL}?{cdx_qs}", timeout_s=timeout_s)
    if cdx_outcome.verdict is not FetchVerdict.ok or cdx_outcome.status_code != 200:
        return None
    try:
        rows = json.loads(cdx_outcome.body)
    except (ValueError, json.JSONDecodeError):
        return None
    # CDX returns a header row + 0+ data rows.
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    timestamp = rows[1][0]
    snap_outcome = await fetch_bytes(_WAYBACK_SNAPSHOT.format(timestamp=timestamp, url=url), timeout_s=timeout_s)
    if snap_outcome.verdict is not FetchVerdict.ok or snap_outcome.status_code != 200:
        return None
    return timestamp, snap_outcome.body.decode("utf-8", errors="replace")


async def _archive_ph_lookup(url: str, *, timeout_s: float) -> str | None:
    """Fetch the archive.ph mirror; returns the snapshot HTML or None."""
    outcome = await fetch_bytes(_ARCHIVE_PH.format(url=url), timeout_s=timeout_s)
    if outcome.verdict is not FetchVerdict.ok or outcome.status_code != 200:
        return None
    return outcome.body.decode("utf-8", errors="replace")


def _snapshot_age_days(timestamp: str) -> int | None:
    """Wayback timestamps are YYYYMMDDhhmmss."""
    try:
        snap_dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return max(0, (datetime.now(UTC) - snap_dt).days)


class ArchiveTier:
    """Wayback + archive.ph hedged fallback. Out-of-band — playbook-dispatched only."""

    name: str = "archive"

    async def fetch(
        self,
        url: str,
        *,
        state: AppState,
        proxy_url: str | None = None,
        conditional_extras: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> TierResult:
        del proxy_url, conditional_extras, kwargs  # Archive tier ignores all today.
        from . import TierResult  # local import — circular with package init

        # Resolve the operator-scaled bound BEFORE dropping `state` — the two
        # lookups below run in a task group and have no settings in scope.
        timeout_s = state.settings.request_timeout(_TIMEOUT_S)
        del state  # archive tier needs no breakers in v0.1
        send, recv = anyio.create_memory_object_stream[_Winner | None](max_buffer_size=2)
        winner: _Winner | None = None

        async def _run_wayback() -> None:
            result = await _wayback_lookup(url, timeout_s=timeout_s)
            if result is None:
                await send.send(None)
                return
            timestamp, html = result
            await send.send(_Winner(source="wayback", html=html, timestamp=timestamp))

        async def _run_archive_ph() -> None:
            html = await _archive_ph_lookup(url, timeout_s=timeout_s)
            await send.send(_Winner(source="archive.ph", html=html) if html else None)

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(_run_wayback)
                tg.start_soon(_run_archive_ph)
                misses = 0
                async with recv:
                    async for item in recv:
                        if item is None:
                            misses += 1
                            if misses >= 2:
                                tg.cancel_scope.cancel()
                                break
                            continue
                        winner = item
                        tg.cancel_scope.cancel()
                        break
        finally:
            await send.aclose()

        if winner is None:
            return TierResult(
                body=b"",
                content_type="text/html",
                status_code=404,
                final_url=url,
                from_archive=True,
                verdict=Verdict.not_found,
            )

        cleaned = _strip_wayback_chrome(winner.html) if winner.source == "wayback" else winner.html
        extracted = await _extract(cleaned, url)
        markdown = extracted.content_md

        from . import Rendered  # local — avoid circular

        snapshot_age_days: int | None = None
        if winner.source == "wayback" and winner.timestamp:
            snapshot_age_days = _snapshot_age_days(winner.timestamp)

        return TierResult(
            body=cleaned.encode("utf-8"),
            content_type="text/html",
            status_code=200,
            final_url=url,
            from_archive=True,
            archive_source=winner.source,
            snapshot_age_days=snapshot_age_days,
            pre_rendered=Rendered(
                content_md=markdown,
                title=extracted.title,
                byline=extracted.byline,
                headings=[Heading(level=h.level, text=h.text) for h in extracted.headings],
                links=[Link(anchor=lk.anchor, href=lk.href, role=lk.role) for lk in extracted.links],
            ),
            verdict=Verdict.ok if markdown else Verdict.length_floor,
        )
