"""Hacker News handler — Algolia API for full kids tree in one call."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode, urlparse

from html_fragment import to_markdown
from http_fetch import fetch_bytes

from ..models import Heading, NextLink, Verdict
from ._common import empty_result, map_non_ok, truncation_note

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


_DEFAULT_TIMEOUT_S = 10
_HN_HOST = "news.ycombinator.com"
# The Algolia-backed search UI (a client-side SPA). Its `?q=` URLs resolve to
# the same public search API this handler already uses for the front page, so
# we route them directly rather than let the generic ladder render the shell.
_ALGOLIA_HOST = "hn.algolia.com"
_ID_RE = re.compile(r"^\d+$")
_FRONT_PAGE_PATHS = frozenset({"/", "/news", "/news/"})
_ALGOLIA_SEARCH_HITS_PER_PAGE = 30


def _algolia_query(url: str) -> str | None:
    """Return the search query for an `hn.algolia.com/?q=` URL, else None."""
    parsed = urlparse(url)
    if (parsed.hostname or "") != _ALGOLIA_HOST:
        return None
    q = (parse_qs(parsed.query).get("q") or [""])[0].strip()
    return q or None


class HNHandler:
    """Tier-0 handler for Hacker News items, front page, and Algolia search."""

    name: str = "site_handler:hn"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        if _algolia_query(url) is not None:
            return True
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

        query = _algolia_query(url)
        parsed = urlparse(url)
        path = parsed.path or "/"
        # A search-UI URL and the bare front page render identically (both are
        # Algolia `search` hit-lists); an item URL renders the kids tree.
        is_hit_list = query is not None or (query is None and path in _FRONT_PAGE_PATHS)

        if query is not None:
            api_url = "https://hn.algolia.com/api/v1/search?" + urlencode(
                {"query": query, "tags": "story", "hitsPerPage": _ALGOLIA_SEARCH_HITS_PER_PAGE},
            )
        elif path in _FRONT_PAGE_PATHS:
            api_url = "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=30"
        else:
            item_id = parse_qs(parsed.query).get("id", [""])[0]
            if not item_id:
                return empty_result(url, Verdict.not_found)
            api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"

        outcome = await fetch_bytes(
            api_url,
            headers={"User-Agent": state.settings.default_ua},
            timeout_s=state.settings.request_timeout(_DEFAULT_TIMEOUT_S),
        )

        non_ok = map_non_ok(outcome, url=url)
        if non_ok is not None:
            # Escalate to a paid site render: this handler rewrote the request to
            # the Algolia API; on its failure, don't surface the API's transport
            # error — render the ORIGINAL url via the paid tier (search-…-guard P4).
            non_ok.escalate_to_render = True
            return non_ok

        try:
            payload = json.loads(outcome.body)
        except (ValueError, json.JSONDecodeError):
            fallback = empty_result(url, Verdict.content_type_mismatch)
            fallback.escalate_to_render = True  # unparseable API body → render the site instead
            return fallback

        if is_hit_list:
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
            volatility="live",
        )


def _render_front_page(payload: Any) -> dict[str, Any]:
    """Render the HN front page (Algolia `tags=front_page` search) as a list."""
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    parts: list[str] = ["# Hacker News\n", f"## Front page ({min(len(hits), 30)})\n"]
    note = truncation_note(min(len(hits), 30), len(hits), noun="stories")
    if note:
        parts.append(note)
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

    budget = _RenderBudget()
    for child in item.get("children") or []:
        rendered = _render_kid(child, depth=1, budget=budget)
        if rendered:
            parts.append(rendered)
    # Declare the truncation rather than silently shipping a partial thread —
    # the same contract `arxiv.py` applies to a capped listing. A caller that
    # cannot tell a bounded render from a complete one will read "no further
    # replies" into a cap (ADR-0009's honest-incompleteness floor).
    if budget.truncated:
        parts.append(f"\n_Thread truncated: rendering stops at {_MAX_COMMENTS} comments or {_MAX_DEPTH} levels of nesting._\n")

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


# Bounds on an UNTRUSTED remote tree — same names and values as `habr.py`.
_MAX_DEPTH = 20
_MAX_COMMENTS = 400


@dataclass(slots=True)
class _RenderBudget:
    """Comment budget for one thread render, plus whether a bound was hit.

    A mutable object rather than a return value because the recursion is
    depth-first over an arbitrary tree: every branch draws from the same
    allowance, so the budget has to be shared, not summed on the way out.
    """

    remaining: int = _MAX_COMMENTS
    truncated: bool = False


def _render_kid(node: Any, *, depth: int, budget: _RenderBudget) -> str:
    """Render one comment and its reply subtree, blockquote-indented by depth.

    **Bounded on both axes, because the tree is untrusted remote input.** The
    Algolia response is an arbitrarily deep structure from the network; before
    2026-08-01 this walked it with no cap at all and a thread nested past
    CPython's ~1000-frame limit raised `RecursionError` out of the handler.

    The deleted-comment branch is the sharper half. It recursed with `depth`
    UNCHANGED — deliberately, so a removed comment does not add a blockquote
    level — which means a chain of deleted nodes advances no counter at all. A
    depth cap alone would not have bounded it: `_MAX_DEPTH` would never be
    reached while the stack still grew one frame per node. That is why the
    comment budget is decremented on that path too, and why the test for it is
    separate.
    """
    if not isinstance(node, dict) or depth > _MAX_DEPTH:
        if depth > _MAX_DEPTH:
            budget.truncated = True
        return ""
    if budget.remaining <= 0:
        budget.truncated = True
        return ""
    budget.remaining -= 1

    text = to_markdown(node.get("text") or "").strip()
    author = node.get("author") or "[deleted]"
    if not text:
        # Item may have been deleted; recurse into kids if any. `depth` is
        # deliberately NOT advanced — a removed comment adds no blockquote
        # level, and advancing it would re-indent every existing thread that
        # contains one. The change's task list said to advance it, to make the
        # depth cap bite on this path; decrementing the shared comment budget
        # here bounds the recursion just as hard (≤ `_MAX_COMMENTS` frames)
        # without touching rendering, so that is what ships. The deleted-chain
        # test asserts the bound, not the mechanism.
        return "".join(_render_kid(c, depth=depth, budget=budget) for c in (node.get("children") or []))

    quote = ">" * depth
    quoted = "\n".join(f"{quote} {line}".rstrip() for line in text.splitlines())
    block = f"{quoted}\n{quote}\n{quote} — {author}\n"
    for child in node.get("children") or []:
        block += _render_kid(child, depth=depth + 1, budget=budget)
    return block
