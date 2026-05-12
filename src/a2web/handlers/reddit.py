"""Reddit handler — fetches comment threads, permalinks, crossposts, and resolves short URLs.

Covers the URL shapes that carry actual discussion content:

  * `/r/<sub>/comments/<id>/<slug>/`           — full thread
  * `/r/<sub>/comments/<id>/<slug>/<comment>/` — permalink, focused render
  * Threads with `crosspost_parent_list`       — annotated header
  * `redd.it/<id>`                             — short URL, HEAD-resolved then recursed
  * Deleted / removed / 404                    — signal for archive escalation

The handler MUST NOT raise on routine HTTP failures; it translates errors
to closed `Verdict` values. Archive escalation is signalled by returning
`Verdict.not_found` with an operator hint — the playbook reads this and
dispatches the archive tier.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import httpx

from ..models import Heading, OperatorHint, Verdict

if TYPE_CHECKING:
    from ..state import AppState
    from ..tiers import TierResult


# --------------------------------------------------------------------- #
# URL shape detection
# --------------------------------------------------------------------- #

# Captures everything: /r/<sub>/comments/<id> with an optional /slug/ and
# an optional /<comment_id>/ (permalink to a specific comment).
_COMMENTS_PATH_RE = re.compile(r"^/r/[^/]+/comments/[^/]+(/|$)")
_PERMALINK_PATH_RE = re.compile(
    r"^/r/(?P<sub>[^/]+)/comments/(?P<post>[^/]+)/(?P<slug>[^/]+)/(?P<comment>[a-z0-9]+)/?$"
)
_REDDIT_HOSTS = frozenset({"reddit.com", "www.reddit.com", "old.reddit.com", "np.reddit.com"})
_SHORT_HOSTS = frozenset({"redd.it"})
_DEFAULT_TIMEOUT_S = 10


def _is_reddit_host(host: str) -> bool:
    return host in _REDDIT_HOSTS


def _is_short_host(host: str) -> bool:
    return host in _SHORT_HOSTS


def _detect_permalink(url: str) -> str | None:
    """Return the focused-comment ID if `url` is a permalink, else None.

    Reddit permalinks look like `/r/X/comments/Y/slug/Z/` where `Z` is a
    base36 comment id. A bare thread URL `/r/X/comments/Y/slug/` has the
    slug as its trailing segment and is NOT a permalink.
    """
    parsed = urlparse(url)
    match = _PERMALINK_PATH_RE.match(parsed.path or "")
    if not match:
        return None
    candidate = match.group("comment")
    # Reddit comment ids are short base36 (typically 6-9 chars). Slugs are
    # longer and contain underscores. A trailing path segment with an
    # underscore is the slug, not a comment id.
    if "_" in candidate or len(candidate) > 12:
        return None
    return candidate


# --------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------- #


class RedditHandler:
    """Site handler for Reddit threads, permalinks, and short URLs."""

    name: str = "site_handler:reddit"

    def matches(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if _is_short_host(host):
            return True
        if _is_reddit_host(host) and _COMMENTS_PATH_RE.match(parsed.path or ""):
            return True
        return False

    async def fetch(self, url: str, *, state: AppState) -> TierResult:
        from ..tiers import TierResult

        parsed = urlparse(url)
        if _is_short_host(parsed.hostname or ""):
            resolved = await _resolve_short_url(url, state=state)
            if resolved is None:
                return _empty_result(url, Verdict.connection_error)
            # If the resolved URL is a comment thread, recurse on it. If
            # not (e.g. resolves to a subreddit listing), surface a
            # no_match so the orchestrator falls through to raw/jina.
            resolved_parsed = urlparse(resolved)
            if _is_reddit_host(resolved_parsed.hostname or "") and _COMMENTS_PATH_RE.match(resolved_parsed.path or ""):
                return await self.fetch(resolved, state=state)
            return TierResult(
                body=b"",
                content_type="",
                status_code=0,
                final_url=resolved,
                no_match=True,
                verdict=Verdict.other,
            )

        permalink_id = _detect_permalink(url)
        json_url = _to_json_url(url, permalink_focus=permalink_id is not None)

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

        if response.status_code == 404:
            return await _fetch_old_reddit_or_archive_signal(url, state=state)
        if response.status_code == 429:
            return _empty_result(url, Verdict.rate_limited)
        if response.status_code == 403:
            # Quarantined / NSFW (unauth) / private — Wayback often has a
            # public capture from before the gate dropped.
            return _archive_escalation_signal(
                url,
                reason="reddit_forbidden_try_archive",
                message="Reddit returned 403 (quarantined/NSFW/private); try archive snapshot.",
            )
        if response.status_code >= 400:
            return _empty_result(url, Verdict.connection_error)

        try:
            payload = response.json()
        except ValueError:
            return _empty_result(url, Verdict.content_type_mismatch)

        rendered = _render_thread(payload, target_comment=permalink_id)
        body_bytes = response.content
        from ..tiers import Rendered

        if rendered.get("is_empty"):
            # Empty thread (deleted / removed). Try old.reddit; if that
            # also fails, signal archive.
            return await _fetch_old_reddit_or_archive_signal(url, state=state)

        return TierResult(
            body=body_bytes,
            content_type="application/json",
            status_code=response.status_code,
            final_url=url,
            headers=dict(response.headers),
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
        )


# --------------------------------------------------------------------- #
# JSON URL construction
# --------------------------------------------------------------------- #


def _to_json_url(url: str, *, permalink_focus: bool = False) -> str:
    """Build the `.json` URL.

    For permalinks, also pass `?context=3` so the API returns the target
    comment's parent ancestry — needed to render the "in response to..."
    context block.
    """
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/") + ".json"
    query = parsed.query
    extra = "limit=500&raw_json=1"
    if permalink_focus:
        extra += "&context=3"
    new_query = f"{query}&{extra}" if query else extra
    return urlunparse(parsed._replace(path=path, query=new_query))


# --------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------- #


def _render_thread(payload: Any, *, target_comment: str | None = None) -> dict[str, Any]:
    """Render a Reddit listing pair `[post, comments]` to markdown.

    If `target_comment` is set, render a focused permalink view:
    OP + a `> in response to ...` context block + the target comment + replies.
    """
    if not (isinstance(payload, list) and len(payload) >= 2):
        return _empty_render()

    post_data = _first_child_data(payload[0])
    comments_data = payload[1].get("data", {}).get("children", []) if isinstance(payload[1], dict) else []

    title = (post_data.get("title") or "").strip() or None
    author = post_data.get("author")
    byline = f"u/{author}" if author and author != "[deleted]" else None
    selftext = (post_data.get("selftext") or "").strip()
    subreddit = post_data.get("subreddit")
    permalink = post_data.get("permalink")
    crosspost = _crosspost_metadata(post_data)
    is_removed = selftext in {"[removed]", "[deleted]"}
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
    if crosspost is not None:
        parts.append(crosspost + "\n")
    if permalink:
        parts.append(f"<https://www.reddit.com{permalink}>\n")
    if selftext and not is_removed:
        parts.append(selftext + "\n")
    elif is_removed:
        parts.append("_[post body removed]_\n")
    parts.append("---\n")

    more_stubs = 0
    if target_comment:
        focus_md, stubs = _render_permalink_focus(comments_data, target_id=target_comment)
        if focus_md:
            parts.append("## Focused comment\n")
            parts.append(focus_md)
        else:
            parts.append("## Comments\n")
            for child in comments_data:
                rendered, child_stubs = _render_comment(child, depth=1)
                if rendered:
                    parts.append(rendered)
                more_stubs += child_stubs
        more_stubs += stubs
    else:
        parts.append("## Comments\n")
        for child in comments_data:
            rendered, child_stubs = _render_comment(child, depth=1)
            if rendered:
                parts.append(rendered)
            more_stubs += child_stubs

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))
    headings.append(Heading(level=2, text="Focused comment" if target_comment else "Comments"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title,
        "byline": byline,
        "headings": headings,
        "more_stubs": more_stubs,
        "is_empty": is_empty,
    }


def _empty_render() -> dict[str, Any]:
    return {
        "content_md": "",
        "title": None,
        "byline": None,
        "headings": [],
        "more_stubs": 0,
        "is_empty": True,
    }


def _crosspost_metadata(post_data: dict[str, Any]) -> str | None:
    """Return a crosspost-source annotation line, or None when not a crosspost."""
    parents = post_data.get("crosspost_parent_list")
    if not isinstance(parents, list) or not parents:
        return None
    parent = parents[0]
    if not isinstance(parent, dict):
        return None
    sub = parent.get("subreddit")
    author = parent.get("author")
    permalink = parent.get("permalink")
    title = (parent.get("title") or "").strip()
    bits: list[str] = ["🔁 Crossposted from"]
    if sub:
        bits.append(f"r/{sub}")
    if author and author != "[deleted]":
        bits.append(f"(u/{author})")
    line = " ".join(bits)
    if permalink:
        line += f" — <https://www.reddit.com{permalink}>"
    if title:
        line += f' — original: "{title}"'
    return line


def _render_permalink_focus(
    comments_data: list[Any], *, target_id: str
) -> tuple[str, int]:
    """Render a focused permalink view.

    The Reddit API with `?context=N` returns the comment ancestry as
    nested `replies`. We walk the tree finding the target id, capture
    its ancestors, then render: ancestors block-quoted with a context
    label, then the focused comment + its replies.
    """
    target_path = _find_comment_path(comments_data, target_id=target_id)
    if not target_path:
        return "", 0

    *ancestors, target = target_path
    parts: list[str] = []
    if ancestors:
        parts.append("> _Context — ancestors of the focused comment:_\n")
        for ancestor_data in ancestors:
            author = ancestor_data.get("author") or "[deleted]"
            body = (ancestor_data.get("body") or "").strip()
            if not body:
                continue
            quoted = "\n".join(f"> {line}".rstrip() for line in body.splitlines())
            parts.append(f"{quoted}\n>\n> — u/{author}\n")

    target_author = target.get("author") or "[deleted]"
    target_body = (target.get("body") or "").strip()
    if target_body:
        parts.append(f"**🎯 Focused comment by u/{target_author}:**\n")
        parts.append(target_body + "\n")

    # Render replies of target one level shallow.
    more_stubs = 0
    target_replies = target.get("replies")
    if isinstance(target_replies, dict):
        for child in target_replies.get("data", {}).get("children", []):
            rendered, stubs = _render_comment(child, depth=1)
            if rendered:
                parts.append(rendered)
            more_stubs += stubs

    return "\n".join(parts), more_stubs


def _find_comment_path(comments_data: list[Any], *, target_id: str) -> list[dict[str, Any]] | None:
    """DFS through the comment tree. Returns the path of `data` dicts
    from the outermost ancestor down to the target, or None if not found.
    """
    for child in comments_data:
        if not isinstance(child, dict):
            continue
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        if not isinstance(data, dict):
            continue
        if data.get("id") == target_id:
            return [data]
        replies = data.get("replies")
        if isinstance(replies, dict):
            inner_children = replies.get("data", {}).get("children", [])
            sub = _find_comment_path(inner_children, target_id=target_id)
            if sub is not None:
                return [data, *sub]
    return None


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


# --------------------------------------------------------------------- #
# Fallbacks: old.reddit + archive signalling
# --------------------------------------------------------------------- #


def _empty_result(url: str, verdict: Verdict) -> TierResult:
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=verdict,
    )


def _archive_escalation_signal(url: str, *, reason: str, message: str) -> TierResult:
    """Return a TierResult that asks the playbook to dispatch the archive tier.

    Used when the handler is confident the content is gone/private at
    source but a Wayback snapshot likely exists. The orchestrator's
    `next_action_after_tier` rule for `Verdict.not_found` on a reddit
    URL produces a `RetryViaArchive` action.
    """
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=Verdict.not_found,
        operator_hint=OperatorHint(code=reason, message=message),
    )


def _to_old_reddit_url(url: str) -> str:
    """Rewrite a reddit URL to old.reddit.com, dropping the .json suffix."""
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    if path.endswith(".json"):
        path = path[: -len(".json")]
    return urlunparse(parsed._replace(netloc="old.reddit.com", path=path, query=""))


async def _resolve_short_url(url: str, *, state: AppState) -> str | None:
    """HEAD `redd.it/<id>` and return the resolved reddit URL, or None."""
    try:
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT_S,
            follow_redirects=True,
            headers={"User-Agent": state.settings.default_ua},
        ) as client:
            response = await client.head(url)
    except httpx.HTTPError:
        return None
    final = str(response.url)
    if not final or final == url:
        return None
    return final


async def _fetch_old_reddit_or_archive_signal(url: str, *, state: AppState) -> TierResult:
    """Try old.reddit HTML; if that also produces nothing, signal archive."""
    result = await _fetch_old_reddit(url, state=state)
    if result.verdict == Verdict.ok and result.pre_rendered is not None:
        return result
    # Old.reddit was no help either — this content is gone at source. Ask
    # the playbook to escalate to Wayback.
    return _archive_escalation_signal(
        url,
        reason="reddit_deleted_try_archive",
        message="Reddit thread returned empty/404 on both API and old.reddit; try archive snapshot.",
    )


async def _fetch_old_reddit(url: str, *, state: AppState) -> TierResult:
    """Fallback: GET old.reddit.com<path> and extract HTML via trafilatura.

    Returns a `Rendered` with extracted markdown on success, else an
    empty result with `not_found` on failure. The caller decides whether
    to bubble the empty result up as an archive-escalation signal.
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
