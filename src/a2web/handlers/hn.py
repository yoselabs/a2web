"""Hacker News handler — Algolia API for full kids tree in one call."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlencode, urlparse

from html_fragment import to_markdown
from http_fetch import fetch_bytes

from ..models import NEXT_LINKS_CAP, Heading, NextLink, Verdict
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
# How many hit-list rows the body renders. Requested from Algolia AND used as
# the render bound, so the two cannot drift — a request for 30 rendered at 25
# would drop five stories with no note, since Algolia's `nbHits` is the only
# total the truncation declaration reads.
_FRONT_PAGE_CAP = 30


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
            api_url = f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={_FRONT_PAGE_CAP}"
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

        items_rendered: int | None = None
        items_advertised: int | None = None
        if is_hit_list:
            rendered = _render_front_page(payload, is_search=query is not None)
            next_links = _front_page_candidates(payload)
            # Declared for the same reason arXiv declares them: the prose says
            # "Showing 30 of 912" and the structured sufficiency signal must
            # reach the same conclusion, or the body and the wire tell the
            # caller different stories.
            hits = payload.get("hits", []) if isinstance(payload, dict) else []
            items_rendered = min(len(hits), _FRONT_PAGE_CAP)
            items_advertised = _source_total(payload, is_search=query is not None)
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
            items_rendered=items_rendered,
            items_advertised=items_advertised,
        )


def _source_total(payload: Any, *, is_search: bool) -> int | None:
    """Algolia's `nbHits` — but ONLY for a real search. Returns `None` otherwise.

    a2web asks for `hitsPerPage=30`, so `len(hits)` can never exceed 30 and a
    note comparing rendered-against-fetched is STRUCTURALLY UNREACHABLE: `shown`
    and `total` are the same number by construction. The declaration existed and
    could not fire. On a SEARCH that is the ADR-0015 harm — a query matching 900
    stories and one matching 30 produced identical, identically silent output,
    and the caller never sees the body.

    **`is_search` is not a nicety.** Measured against the live API 2026-08-01:

        tags=front_page&hitsPerPage=30  → nbHits 171, hits 30
        query=rust&tags=story           → nbHits 59173, hits 30

    For the search, 59173 is the real match count and "30 of 59173" is true and
    useful. For the front page it is NOT: `front_page` tags a rolling window of
    recently-front-paged stories, while THE front page is the 30 currently on
    it. Declaring "30 of 171" tells the caller it is missing 141 front-page
    stories that do not exist as such — a false `listing_partial`.

    A false "incomplete" is worse than none: it teaches the caller to ignore the
    signal, which costs every TRUE partial that follows. This is why
    `fix-cache-ttl-and-listing-sufficiency` §4.7 left hn open rather than guess,
    and the guess was made anyway before the numbers above were measured.
    """
    if not is_search or not isinstance(payload, dict):
        return None
    total = payload.get("nbHits")
    return total if isinstance(total, int) else None


def _render_front_page(payload: Any, *, is_search: bool = False) -> dict[str, Any]:
    """Render an Algolia hit-list (the front page, or a search) as a list."""
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    parts: list[str] = ["# Hacker News\n", f"## Front page ({min(len(hits), _FRONT_PAGE_CAP)})\n"]
    note = truncation_note(min(len(hits), _FRONT_PAGE_CAP), _source_total(payload, is_search=is_search), noun="stories")
    if note:
        parts.append(note)
    count = 0
    for hit in hits[:_FRONT_PAGE_CAP]:
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
    """Build up to `NEXT_LINKS_CAP` NextLink entries from the front-page hits.

    External-link stories → drilldown to the external URL. Text-only stories
    → drilldown to the discussion page on news.ycombinator.com.
    """
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    out: list[NextLink] = []
    for hit in hits:
        if len(out) >= NEXT_LINKS_CAP:
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
