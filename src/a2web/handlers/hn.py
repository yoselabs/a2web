"""Hacker News handler — Algolia API for full kids tree in one call."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import httpx

from ..models import Heading, Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


_DEFAULT_TIMEOUT_S = 10
_HN_HOST = "news.ycombinator.com"
_ID_RE = re.compile(r"^\d+$")


class HNHandler:
    """Tier-0 handler for Hacker News items."""

    name: str = "site_handler:hn"

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        if (parsed.hostname or "") != _HN_HOST:
            return False
        if (parsed.path or "/") != "/item":
            return False
        item_id = parse_qs(parsed.query).get("id", [""])[0]
        return bool(_ID_RE.match(item_id))

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..tiers import TierResult

        item_id = parse_qs(urlparse(url).query).get("id", [""])[0]
        if not item_id:
            return _empty_result(url, Verdict.not_found)

        algolia_url = f"https://hn.algolia.com/api/v1/items/{item_id}"
        try:
            async with httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": state.settings.default_ua},
            ) as client:
                response = await client.get(algolia_url)
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
            payload = response.json()
        except ValueError:
            return _empty_result(url, Verdict.content_type_mismatch)

        rendered = _render_item(payload)
        from ..tiers import Rendered

        return TierResult(
            body=response.content,
            content_type="application/json",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
        )


def _render_item(item: Any) -> dict[str, Any]:
    """Render an Algolia item with its `kids` tree to markdown."""
    if not isinstance(item, dict):
        return {"content_md": "", "title": None, "byline": None, "headings": []}

    title = (item.get("title") or "").strip() or None
    author = item.get("author")
    byline = author if author else None
    text = _strip_html(item.get("text") or "")
    item_url = item.get("url")

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    if byline:
        parts.append(f"by {byline}\n")
    if item_url:
        parts.append(f"<{item_url}>\n")
    if text:
        parts.append(text + "\n")
    parts.append("---\n")
    parts.append("## Comments\n")

    for child in item.get("children") or []:
        rendered = _render_kid(child, depth=1)
        if rendered:
            parts.append(rendered)

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))
    headings.append(Heading(level=2, text="Comments"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title,
        "byline": byline,
        "headings": headings,
    }


def _render_kid(node: Any, *, depth: int) -> str:
    if not isinstance(node, dict):
        return ""
    text = _strip_html(node.get("text") or "").strip()
    author = node.get("author") or "[deleted]"
    if not text:
        # Item may have been deleted; recurse into kids if any
        return "".join(_render_kid(c, depth=depth) for c in (node.get("children") or []))

    quote = ">" * depth
    quoted = "\n".join(f"{quote} {line}".rstrip() for line in text.splitlines())
    block = f"{quoted}\n{quote}\n{quote} — {author}\n"
    for child in node.get("children") or []:
        block += _render_kid(child, depth=depth + 1)
    return block


def _strip_html(html: str) -> str:
    """Lightweight HTML → text. Algolia returns minimal HTML in `text` fields."""
    if not html:
        return ""
    text = html
    text = re.sub(r"<\s*p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?\s*i\s*>", "*", text, flags=re.IGNORECASE)
    text = re.sub(r"</?\s*b\s*>", "**", text, flags=re.IGNORECASE)
    text = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&#39;", "'")
    )
    return text.strip()


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
