"""Reddit comment-thread handler — fetches `<url>.json` and renders markdown.

Handles `<host>/r/<sub>/comments/<id>...` URLs. The handler MUST NOT raise
on routine HTTP failures; it translates errors to closed `Verdict` values.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import httpx

from ..models import Heading, Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


_COMMENTS_PATH_RE = re.compile(r"^/r/[^/]+/comments/[^/]+(/|$)")
_REDDIT_HOSTS = frozenset({"reddit.com", "www.reddit.com", "old.reddit.com"})
_DEFAULT_TIMEOUT_S = 10


def _is_reddit_host(host: str) -> bool:
    return host in _REDDIT_HOSTS


class RedditHandler:
    """Tier-0 handler for Reddit comment threads."""

    name: str = "site_handler:reddit"

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        return _is_reddit_host(parsed.hostname or "") and bool(_COMMENTS_PATH_RE.match(parsed.path or ""))

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..tiers import TierResult

        json_url = _to_json_url(url)
        try:
            async with httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT_S,
                follow_redirects=True,
                headers={"User-Agent": state.settings.default_ua},
            ) as client:
                response = await client.get(json_url)
        except httpx.TimeoutException:
            return _empty_result(url, Verdict.timeout)
        except httpx.HTTPError:
            return _empty_result(url, Verdict.connection_error)

        # v0.3: on 404, try old.reddit.com as HTML fallback before giving up.
        # Reddit frequently 404s its `.json` endpoint for threads that are
        # still readable on old.reddit (private/removed quirks, UA gating).
        if response.status_code == 404:
            return await _fetch_old_reddit(url, state=state)
        if response.status_code == 429:
            return _empty_result(url, Verdict.rate_limited)
        if response.status_code >= 400:
            return _empty_result(url, Verdict.connection_error)

        try:
            payload = response.json()
        except ValueError:
            return _empty_result(url, Verdict.content_type_mismatch)

        rendered = _render_thread(payload)
        body_bytes = response.content
        from ..tiers import Rendered  # local — avoid circular

        # v0.3: empty thread (deleted / quarantined / private) → fall back to
        # old.reddit. is_empty=True when JSON parsed but had no title, no
        # selftext, and no comments — boilerplate "---/Comments" body alone
        # doesn't count as a renderable thread.
        if rendered.get("is_empty"):
            return await _fetch_old_reddit(url, state=state)

        return TierResult(
            body=body_bytes,
            content_type="application/json",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
        )


def _to_json_url(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/") + ".json"
    query = parsed.query
    extra = "limit=500&raw_json=1"
    new_query = f"{query}&{extra}" if query else extra
    return urlunparse(parsed._replace(path=path, query=new_query))


def _render_thread(payload: Any) -> dict[str, Any]:
    """Render a Reddit listing pair `[post, comments]` to markdown."""
    if not (isinstance(payload, list) and len(payload) >= 2):
        return {
            "content_md": "",
            "title": None,
            "byline": None,
            "headings": [],
            "more_stubs": 0,
            "is_empty": True,
        }

    post_data = _first_child_data(payload[0])
    comments_data = payload[1].get("data", {}).get("children", []) if isinstance(payload[1], dict) else []

    title = (post_data.get("title") or "").strip() or None
    author = post_data.get("author")
    byline = f"u/{author}" if author and author != "[deleted]" else None
    selftext = (post_data.get("selftext") or "").strip()
    subreddit = post_data.get("subreddit")
    permalink = post_data.get("permalink")
    is_empty = title is None and not selftext and not comments_data

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    meta_line: list[str] = []
    if byline:
        meta_line.append(f"by {byline}")
    if subreddit:
        meta_line.append(f"in r/{subreddit}")
    if meta_line:
        parts.append(" ".join(meta_line) + "\n")
    if permalink:
        parts.append(f"<https://www.reddit.com{permalink}>\n")
    if selftext:
        parts.append(selftext + "\n")
    parts.append("---\n")
    parts.append("## Comments\n")

    more_stubs = 0
    for child in comments_data:
        rendered, stubs = _render_comment(child, depth=1)
        if rendered:
            parts.append(rendered)
        more_stubs += stubs

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))
    headings.append(Heading(level=2, text="Comments"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title,
        "byline": byline,
        "headings": headings,
        "more_stubs": more_stubs,
        "is_empty": is_empty,
    }


def _first_child_data(listing: Any) -> dict[str, Any]:
    if not isinstance(listing, dict):
        return {}
    children = listing.get("data", {}).get("children", [])
    if not children:
        return {}
    first = children[0]
    if not isinstance(first, dict):
        return {}
    data = first.get("data", {})
    return data if isinstance(data, dict) else {}


def _render_comment(node: Any, *, depth: int) -> tuple[str, int]:
    """Render one comment subtree. Returns (markdown, count_of_more_stubs)."""
    if not isinstance(node, dict):
        return "", 0
    kind = node.get("kind")
    data = node.get("data", {})
    if not isinstance(data, dict):
        return "", 0

    if kind == "more":
        return "", int(data.get("count", 0) or 0)

    body = (data.get("body") or "").strip()
    author = data.get("author") or "[deleted]"
    if not body:
        return "", 0

    quote = ">" * depth
    quoted_body = "\n".join(f"{quote} {line}".rstrip() for line in body.splitlines())
    block = f"{quoted_body}\n{quote}\n{quote} — u/{author}\n"

    more_stubs = 0
    replies = data.get("replies")
    if isinstance(replies, dict):
        for child in replies.get("data", {}).get("children", []):
            rendered, stubs = _render_comment(child, depth=depth + 1)
            if rendered:
                block += rendered
            more_stubs += stubs

    return block, more_stubs


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )


def _to_old_reddit_url(url: str) -> str:
    """Rewrite a reddit URL to old.reddit.com, dropping the .json suffix."""
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    if path.endswith(".json"):
        path = path[: -len(".json")]
    return urlunparse(parsed._replace(netloc="old.reddit.com", path=path, query=""))


async def _fetch_old_reddit(url: str, *, state: AppState) -> TierResult:
    """Fallback: GET old.reddit.com<path> and extract HTML via trafilatura.

    Used when the primary `.json` request fails (404, deleted/private thread,
    or any other case where the JSON path produces no usable content). Reddit
    still serves a server-rendered HTML thread at the old.reddit.com host for
    many threads where the JSON API refuses. Returns a `Rendered` with the
    extracted markdown, or an empty result with `not_found` on failure.
    """
    import trafilatura

    from ..tiers import Rendered, TierResult

    old_url = _to_old_reddit_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT_S,
            follow_redirects=True,
            headers={"User-Agent": state.settings.default_ua},
        ) as client:
            response = await client.get(old_url)
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

    markdown = (
        trafilatura.extract(
            html,
            url=old_url,
            output_format="markdown",
            include_comments=True,
            include_tables=False,
        )
        or ""
    )
    if not markdown:
        return _empty_result(url, Verdict.length_floor)

    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata else None) or None
    author = (metadata.author if metadata else None) or None
    byline = author if author else None

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))

    return TierResult(
        body=response.content,
        content_type="text/html",
        status_code=response.status_code,
        final_url=old_url,
        headers=dict(response.headers),
        pre_rendered=Rendered(
            content_md=markdown,
            title=title,
            byline=byline,
            headings=headings,
        ),
        verdict=Verdict.ok,
    )
