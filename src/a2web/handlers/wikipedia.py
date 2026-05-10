"""Wikipedia handler — Parsoid REST API for clean article HTML.

Match: `<lang>.wikipedia.org/wiki/<title>`. REST API returns HTML that
trafilatura handles cleanly — much smaller than the live page (no nav,
sidebar, edit links, or interaction surface).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

import httpx
import trafilatura

from ..models import Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


_WIKI_HOST_RE = re.compile(r"^([a-z]{2,3})\.wikipedia\.org$", re.IGNORECASE)
_WIKI_PATH_RE = re.compile(r"^/wiki/([^?#]+)$")
_TIMEOUT_S = 10.0


def _parse(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host_match = _WIKI_HOST_RE.match(parsed.hostname or "")
    if host_match is None:
        return None
    path_match = _WIKI_PATH_RE.match(parsed.path or "")
    if path_match is None:
        return None
    return host_match.group(1).lower(), path_match.group(1)


class WikipediaHandler:
    """Tier-0 handler for Wikipedia article URLs."""

    name: str = "site_handler:wikipedia"

    def matches(self, url: str) -> bool:
        return _parse(url) is not None

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..tiers import TierResult

        parsed = _parse(url)
        if parsed is None:
            return _empty_result(url, Verdict.not_found)
        lang, slug = parsed

        api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{slug}"
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_S,
                follow_redirects=True,
                headers={
                    "User-Agent": state.settings.default_ua,
                    "Accept": "text/html",
                },
            ) as client:
                response = await client.get(api_url)
        except httpx.TimeoutException:
            return _empty_result(url, Verdict.timeout)
        except httpx.HTTPError:
            return _empty_result(url, Verdict.connection_error)

        if response.status_code == 404:
            return _empty_result(url, Verdict.not_found)
        if response.status_code == 429:
            return _empty_result(url, Verdict.rate_limited)
        if response.status_code >= 400:
            return _empty_result(url, Verdict.connection_error)

        html = response.text
        if not html:
            return _empty_result(url, Verdict.length_floor)

        title = unquote(slug).replace("_", " ")
        markdown = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
        ) or ""

        if not markdown:
            return _empty_result(url, Verdict.length_floor)

        rendered = {
            "content_md": markdown,
            "title": title,
            "byline": None,
            "headings": [],
        }
        return TierResult(
            body=html.encode("utf-8"),
            content_type="text/html",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            tier_extras={"pre_rendered": rendered},
            verdict=Verdict.ok,
        )


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
