"""Wikipedia handler — Parsoid REST API for clean article HTML.

Match: `<lang>.wikipedia.org/wiki/<title>`. REST API returns HTML that
trafilatura handles cleanly — much smaller than the live page (no nav,
sidebar, edit links, or interaction surface).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlparse

import trafilatura

from ..models import NextLink, Verdict
from ..packages.http_fetch import fetch_bytes
from ._common import empty_result, map_non_ok

if TYPE_CHECKING:
    from ..settings import AppSettings
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

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        return _parse(url) is not None

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import TierResult

        parsed = _parse(url)
        if parsed is None:
            return empty_result(url, Verdict.not_found)
        lang, slug = parsed

        api_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/html/{slug}"
        outcome = await fetch_bytes(
            api_url,
            headers={"User-Agent": state.settings.default_ua, "Accept": "text/html"},
            timeout_s=_TIMEOUT_S,
        )

        non_ok = map_non_ok(outcome, url=url)
        if non_ok is not None:
            return non_ok

        html = outcome.body.decode("utf-8", errors="replace")
        if not html:
            return empty_result(url, Verdict.length_floor)

        title = unquote(slug).replace("_", " ")
        markdown = (
            trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_comments=False,
                include_tables=True,
            )
            or ""
        )

        if not markdown:
            return empty_result(url, Verdict.length_floor)

        from ..tiers import Rendered

        next_links = _wikilink_candidates(html, lang=lang)

        return TierResult(
            body=outcome.body,
            content_type="text/html",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered(content_md=markdown, title=title),
            next_links=next_links,
            verdict=Verdict.ok,
        )


# --------------------------------------------------------------------- #
# Wikilink extraction (v0.7 link-discovery)
# --------------------------------------------------------------------- #

_WIKILINK_RE = re.compile(
    r'<a\s+[^>]*href="/wiki/(?P<target>[^"#:?]+)"[^>]*>(?P<anchor>[^<]+)</a>',
    re.IGNORECASE,
)


def _wikilink_candidates(html: str, *, lang: str) -> list[NextLink]:
    """Pull up to 10 outbound article wikilinks from Parsoid HTML.

    Wikipedia's REST output renders internal article links as `<a href="/wiki/X">Y</a>`.
    Namespaced links (File:, Category:, Help:, etc.) carry a `:` in the target and
    are filtered out — we want article-to-article links only. Deduplicates on target.
    External citations (`<a class="external" href="https://...">`) live elsewhere
    and are not in scope for v0.7 (deferred per spec).
    """
    seen: set[str] = set()
    out: list[NextLink] = []
    for match in _WIKILINK_RE.finditer(html):
        if len(out) >= 10:
            break
        target = match.group("target")
        if target in seen:
            continue
        anchor = (match.group("anchor") or "").strip()
        if not anchor or not target:
            continue
        seen.add(target)
        out.append(
            NextLink(
                anchor=anchor,
                url=f"https://{lang}.wikipedia.org/wiki/{target}",
                reason="related article",
                kind="related",
            ),
        )
    return out
