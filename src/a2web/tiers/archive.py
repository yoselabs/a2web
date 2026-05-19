"""Archive tier — hedged Wayback CDX + archive.ph fallback.

Out-of-band tier: registered but NOT in `TIER_ORDER`. The orchestrator
dispatches it only when the playbook returns `RetryViaArchive`.

Hedge strategy: launch both upstreams under an anyio task group, write
to a single capacity-1 send stream on first success, cancel the loser
on task-group exit.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import anyio
import httpx
import trafilatura
from curl_cffi import requests as curl_requests
from curl_cffi.requests import exceptions as curl_exceptions

from ..models import Verdict


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
_IMPERSONATE = "chrome120"

_WAYBACK_CHROME_RE = re.compile(
    r"<!--\s*BEGIN WAYBACK TOOLBAR INSERT.*?<!--\s*END WAYBACK TOOLBAR INSERT\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_WAYBACK_DIV_RE = re.compile(r'<div id="wm-ipp-base".*?</div>', re.DOTALL | re.IGNORECASE)


def _strip_wayback_chrome(html: str) -> str:
    html = _WAYBACK_CHROME_RE.sub("", html)
    return _WAYBACK_DIV_RE.sub("", html)


def _to_markdown(html: str, url: str) -> str:
    md = trafilatura.extract(html, url=url, output_format="markdown", include_comments=False, include_tables=True)
    return md or ""


async def _wayback_lookup(url: str) -> tuple[str, str] | None:
    """Return (timestamp, snapshot_html) or None."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_S, follow_redirects=True) as client:
        try:
            resp = await client.get(_CDX_URL, params={"url": url, "output": "json", "limit": 1, "fl": "timestamp,original"})
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            rows = resp.json()
        except ValueError:
            return None
        # CDX returns a header row + 0+ data rows.
        if not isinstance(rows, list) or len(rows) < 2:
            return None
        timestamp = rows[1][0]
        try:
            snap = await client.get(_WAYBACK_SNAPSHOT.format(timestamp=timestamp, url=url))
        except httpx.HTTPError:
            return None
        if snap.status_code != 200:
            return None
        return timestamp, snap.text


def _archive_ph_sync(url: str) -> str | None:
    """Synchronous archive.ph fetch via curl_cffi (run in to_thread)."""
    try:
        resp = curl_requests.get(
            _ARCHIVE_PH.format(url=url),
            impersonate=_IMPERSONATE,
            timeout=_TIMEOUT_S,
            allow_redirects=True,
        )
    except (curl_exceptions.RequestException, OSError):
        return None
    if resp.status_code != 200:
        return None
    return resp.text


async def _archive_ph_lookup(url: str) -> str | None:
    return await asyncio.to_thread(_archive_ph_sync, url)


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

        del state  # archive tier needs no breakers in v0.1
        send, recv = anyio.create_memory_object_stream[_Winner | None](max_buffer_size=2)
        winner: _Winner | None = None

        async def _run_wayback() -> None:
            result = await _wayback_lookup(url)
            if result is None:
                await send.send(None)
                return
            timestamp, html = result
            await send.send(_Winner(source="wayback", html=html, timestamp=timestamp))

        async def _run_archive_ph() -> None:
            html = await _archive_ph_lookup(url)
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
        markdown = _to_markdown(cleaned, url)

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
            pre_rendered=Rendered(content_md=markdown),
            verdict=Verdict.ok if markdown else Verdict.length_floor,
        )
