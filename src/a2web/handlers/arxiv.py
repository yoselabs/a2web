"""arxiv handler — export.arxiv.org Atom API for clean abstract pages.

Match: `arxiv.org/abs/<id>`. The PR7b playbook rewrites pdf URLs to abs
before this runs, so we don't need to handle pdf paths here.

API: `GET https://export.arxiv.org/api/query?id_list=<id>` returns Atom
XML with one entry per id. Empty entry list = unknown id (not_found).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from ..models import Heading, NextLink, Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


_ARXIV_ID_RE = re.compile(r"^/abs/([^/?#]+?)(?:v\d+)?/?$", re.IGNORECASE)
_ARXIV_LIST_RE = re.compile(r"^/list/(?P<cat>[A-Za-z][A-Za-z\-\.]*)/(?P<window>\d{4,6}|recent|new)/?$", re.IGNORECASE)
_ARXIV_HOSTS = frozenset({"arxiv.org", "www.arxiv.org"})
_API_URL = "https://export.arxiv.org/api/query"
_LIST_URL = "https://arxiv.org/list"
_TIMEOUT_S = 10.0
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _extract_id(url: str) -> str | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _ARXIV_HOSTS:
        return None
    match = _ARXIV_ID_RE.match(parsed.path or "")
    return match.group(1) if match else None


def _extract_listing(url: str) -> tuple[str, str] | None:
    """Return `(category, window)` for an arxiv `/list/<cat>/<yymm|recent>` URL."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _ARXIV_HOSTS:
        return None
    match = _ARXIV_LIST_RE.match(parsed.path or "")
    if not match:
        return None
    return match.group("cat"), match.group("window")


class ArxivHandler:
    """Tier-0 handler for arxiv.org/abs/<id> and arxiv.org/list/<cat>/<window> URLs."""

    name: str = "site_handler:arxiv"

    def matches(self, url: str) -> bool:
        return _extract_id(url) is not None or _extract_listing(url) is not None

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..tiers import Rendered, TierResult

        listing = _extract_listing(url)
        if listing is not None:
            return await self._fetch_listing(url, listing=listing, state=state)

        arxiv_id = _extract_id(url)
        if arxiv_id is None:
            return _empty_result(url, Verdict.not_found)

        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": state.settings.default_ua},
            ) as client:
                response = await client.get(_API_URL, params={"id_list": arxiv_id})
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

        try:
            root = ET.fromstring(response.text)  # noqa: S314 — arxiv API is trusted; httpx caps payload
        except ET.ParseError:
            return _empty_result(url, Verdict.content_type_mismatch)

        entry = root.find("atom:entry", _NS)
        if entry is None:
            return _empty_result(url, Verdict.not_found)

        rendered = _render_entry(entry)

        return TierResult(
            body=response.content,
            content_type="application/atom+xml",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
        )

    async def _fetch_listing(
        self,
        url: str,
        *,
        listing: tuple[str, str],
        state: AppState,
    ) -> TierResult:
        from ..tiers import Rendered, TierResult

        cat, window = listing
        list_url = f"{_LIST_URL}/{cat}/{window}"
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": state.settings.default_ua},
            ) as client:
                response = await client.get(list_url)
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

        entries = _parse_listing_entries(response.text)
        rendered = _render_listing(cat, window, entries)
        next_links = _listing_candidates(entries)

        return TierResult(
            body=response.content,
            content_type="text/html",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            pre_rendered=Rendered.from_dict(rendered),
            next_links=next_links,
            verdict=Verdict.ok,
        )


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return re.sub(r"\s+", " ", el.text).strip()


def _render_entry(entry: ET.Element) -> dict[str, object]:
    title = _text(entry.find("atom:title", _NS))
    summary = _text(entry.find("atom:summary", _NS))

    authors: list[str] = []
    for author_el in entry.findall("atom:author", _NS):
        name = _text(author_el.find("atom:name", _NS))
        if name:
            authors.append(name)
    byline = ", ".join(authors) if authors else None

    categories: list[str] = []
    for cat_el in entry.findall("atom:category", _NS):
        term = cat_el.attrib.get("term")
        if term:
            categories.append(term)

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    if byline:
        parts.append(f"_{byline}_\n")
    if summary:
        parts.append(summary + "\n")
    if categories:
        parts.append("\n## Categories\n")
        for cat in categories:
            parts.append(f"- {cat}")

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))
    if categories:
        headings.append(Heading(level=2, text="Categories"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title or None,
        "byline": byline,
        "headings": headings,
    }


# --------------------------------------------------------------------- #
# Listing parsing (v0.7 link-discovery)
# --------------------------------------------------------------------- #

_LIST_ABS_RE = re.compile(
    r'<a href="/abs/(?P<id>[^"]+?)"[^>]*>arXiv:(?P=id)</a>',
    re.IGNORECASE,
)
_LIST_TITLE_RE = re.compile(
    r'<div class="list-title[^"]*"[^>]*>\s*<span class="descriptor">\s*Title:\s*</span>\s*(?P<title>.+?)</div>',
    re.IGNORECASE | re.DOTALL,
)
_LIST_AUTHORS_RE = re.compile(
    r'<div class="list-authors"[^>]*>\s*<span class="descriptor">\s*Authors?:\s*</span>\s*(?P<authors>.+?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def _parse_listing_entries(html: str) -> list[dict[str, str]]:
    """Pull (id, title, authors) for each entry on an arxiv listing page.

    Listing pages are well-known stable HTML — sequential `<dt>...<dd>...` blocks.
    Walk by abs-id anchor matches and pair each with the nearest title/authors div
    that follows it in document order.
    """
    out: list[dict[str, str]] = []
    abs_matches = list(_LIST_ABS_RE.finditer(html))
    for i, match in enumerate(abs_matches):
        abs_id = match.group("id")
        slice_end = abs_matches[i + 1].start() if i + 1 < len(abs_matches) else len(html)
        block = html[match.end() : slice_end]
        title_match = _LIST_TITLE_RE.search(block)
        authors_match = _LIST_AUTHORS_RE.search(block)
        title = re.sub(r"\s+", " ", title_match.group("title")).strip() if title_match else abs_id
        authors_raw = re.sub(r"<[^>]+>", "", authors_match.group("authors")) if authors_match else ""
        authors = re.sub(r"\s+", " ", authors_raw).strip()
        out.append({"id": abs_id, "title": title, "authors": authors})
    return out


def _render_listing(cat: str, window: str, entries: list[dict[str, str]]) -> dict[str, object]:
    """Render an arxiv listing as a terse list."""
    title_text = f"arXiv · {cat} · {window}"
    parts: list[str] = [f"# {title_text}\n", f"## Papers ({min(len(entries), 25)})\n"]
    for entry in entries[:25]:
        parts.append(f"- **{entry['title']}** ({entry['authors']})\n  <https://arxiv.org/abs/{entry['id']}>")
    headings: list[Heading] = [
        Heading(level=1, text=title_text),
        Heading(level=2, text=f"Papers ({min(len(entries), 25)})"),
    ]
    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title_text,
        "byline": None,
        "headings": headings,
    }


def _listing_candidates(entries: list[dict[str, str]]) -> list[NextLink]:
    """Build up to 10 NextLink entries from listing entries.

    `reason` is the comma-joined first authors (truncated to the model's 80-char cap).
    """
    out: list[NextLink] = []
    for entry in entries[:10]:
        out.append(
            NextLink(
                anchor=entry["title"],
                url=f"https://arxiv.org/abs/{entry['id']}",
                reason=entry["authors"] or "abstract",
                kind="drilldown",
            ),
        )
    return out


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
