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

from ..models import Heading, Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


_ARXIV_ID_RE = re.compile(r"^/abs/([^/?#]+?)(?:v\d+)?/?$", re.IGNORECASE)
_ARXIV_HOSTS = frozenset({"arxiv.org", "www.arxiv.org"})
_API_URL = "https://export.arxiv.org/api/query"
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


class ArxivHandler:
    """Tier-0 handler for arxiv.org/abs/<id> URLs."""

    name: str = "site_handler:arxiv"

    def matches(self, url: str) -> bool:
        return _extract_id(url) is not None

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..tiers import TierResult

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
        from ..tiers import Rendered

        return TierResult(
            body=response.content,
            content_type="application/atom+xml",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            pre_rendered=Rendered.from_dict(rendered),
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


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
