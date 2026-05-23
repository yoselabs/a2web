"""Hacker News handler — Algolia API for full kids tree in one call."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from ..models import Heading, NextLink, Verdict
from ..packages.html_fragment import to_markdown
from ..packages.http_fetch import FetchVerdict, fetch_bytes

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


_DEFAULT_TIMEOUT_S = 10
_HN_HOST = "news.ycombinator.com"
_ID_RE = re.compile(r"^\d+$")
_FRONT_PAGE_PATHS = frozenset({"/", "/news", "/news/"})


class HNHandler:
    """Tier-0 handler for Hacker News items and front page."""

    name: str = "site_handler:hn"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        parsed = urlparse(url)
        if (parsed.hostname or "") != _HN_HOST:
            return False
        path = parsed.path or "/"
        if path in _FRONT_PAGE_PATHS:
            return True
        if path != "/item":
            return False
        item_id = parse_qs(parsed.query).get("id", [""])[0]
        return bool(_ID_RE.match(item_id))

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import Rendered, TierResult

        parsed = urlparse(url)
        path = parsed.path or "/"
        is_front_page = path in _FRONT_PAGE_PATHS

        if is_front_page:
            api_url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"
        else:
            item_id = parse_qs(parsed.query).get("id", [""])[0]
            if not item_id:
                return _empty_result(url, Verdict.not_found)
            api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"

        outcome = await fetch_bytes(
            api_url,
            headers={"User-Agent": state.settings.default_ua},
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

        if outcome.verdict is FetchVerdict.timeout:
            return _empty_result(url, Verdict.timeout)
        if outcome.verdict is FetchVerdict.not_found:
            return _empty_result(url, Verdict.not_found)
        if outcome.verdict is FetchVerdict.rate_limited:
            return _empty_result(url, Verdict.rate_limited)
        if outcome.verdict is not FetchVerdict.ok:
            return _empty_result(url, Verdict.connection_error)

        try:
            payload = json.loads(outcome.body)
        except (ValueError, json.JSONDecodeError):
            return _empty_result(url, Verdict.content_type_mismatch)

        if is_front_page:
            rendered = _render_front_page(payload)
            next_links = _front_page_candidates(payload)
        else:
            rendered = _render_item(payload)
            next_links = []

        return TierResult(
            body=outcome.body,
            content_type="application/json",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered.from_dict(rendered),
            next_links=next_links,
            verdict=Verdict.ok,
        )


def _render_front_page(payload: Any) -> dict[str, Any]:
    """Render the HN front page (Algolia `tags=front_page` search) as a list."""
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    parts: list[str] = ["# Hacker News\n", f"## Front page ({min(len(hits), 30)})\n"]
    count = 0
    for hit in hits[:30]:
        if not isinstance(hit, dict):
            continue
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        points = hit.get("points", 0) or 0
        num_comments = hit.get("num_comments", 0) or 0
        discussion = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        external = hit.get("url")
        # External-link stories expose both the article and the HN discussion;
        # text-only stories have just the discussion page.
        if external:
            links_md = f"[article]({external}) · [discussion]({discussion})"
        else:
            links_md = f"[discussion]({discussion})"
        parts.append(f"- **{title}** ({points} points, {num_comments} comments)\n  {links_md}")
        count += 1
    headings = [
        Heading(level=1, text="Hacker News"),
        Heading(level=2, text=f"Front page ({count})"),
    ]
    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": "Hacker News",
        "byline": None,
        "headings": headings,
    }


def _front_page_candidates(payload: Any) -> list[NextLink]:
    """Build up to 10 NextLink entries from the front-page hits.

    External-link stories → drilldown to the external URL. Text-only stories
    → drilldown to the discussion page on news.ycombinator.com.
    """
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    out: list[NextLink] = []
    for hit in hits:
        if len(out) >= 10:
            break
        if not isinstance(hit, dict):
            continue
        title = (hit.get("title") or "").strip()
        object_id = hit.get("objectID")
        if not title or not object_id:
            continue
        points = hit.get("points", 0) or 0
        num_comments = hit.get("num_comments", 0) or 0
        external_url = hit.get("url")
        link = external_url or f"https://news.ycombinator.com/item?id={object_id}"
        out.append(
            NextLink(
                anchor=title,
                url=link,
                reason=f"{points} points, {num_comments} comments",
                kind="drilldown",
            ),
        )
    return out


def _render_item(item: Any) -> dict[str, Any]:
    """Render an Algolia item with its `kids` tree to markdown."""
    if not isinstance(item, dict):
        return {"content_md": "", "title": None, "byline": None, "headings": []}

    title = (item.get("title") or "").strip() or None
    author = item.get("author")
    byline = author if author else None
    text = to_markdown(item.get("text") or "")
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
    text = to_markdown(node.get("text") or "").strip()
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


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )
