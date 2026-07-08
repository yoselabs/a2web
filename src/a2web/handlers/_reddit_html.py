"""Pure old.reddit URL normalization + flat-HTML parsing (`reddit-via-zyte`).

Two concerns, no I/O, no settings — a handler-adjacent microsofware helper:

1. **`normalize(url)`** maps any Reddit URL shape an agent sends to the channel
   proven to return content: a **thread** URL becomes the canonical
   `https://old.reddit.com/r/<sub>/comments/<id>/<slug>/?limit=500&sort=top`
   (old.reddit renders ~500 flat scored comments server-side in one load); a
   **listing/search** URL becomes its new-reddit (`www.reddit.com`) canonical.
   It NEVER emits a `.json` endpoint (walled; ADR-0011).

2. **`parse_thread(html)`** parses old.reddit's server-rendered flat HTML into a
   typed `RedditThread` — the post plus its comments with author, score, body,
   and nesting depth — via `selectolax` CSS selectors (no shreddit
   web-components, trafilatura-independent). It also reads the **comment-total
   oracle** off the post's `N comments` bylink, the authoritative count the
   content-expectations contract asserts loaded comments against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlencode, urlparse, urlunparse

from html_fragment import to_markdown
from selectolax.parser import HTMLParser, Node

Channel = Literal["thread", "listing"]

# `/r/<sub>/comments/<id>[/<slug>[/<focused-comment>]]` — the thread shape.
_COMMENTS_RE = re.compile(r"^/r/(?P<sub>[^/]+)/comments/(?P<id>[^/]+)(?:/(?P<slug>[^/]+))?")
_COUNT_RE = re.compile(r"(\d[\d,]*)")


# --------------------------------------------------------------------- #
# URL normalization
# --------------------------------------------------------------------- #


def normalize(url: str) -> tuple[Channel, str]:
    """Map a Reddit URL to `(channel, canonical_url)`.

    Thread/comment URLs (any `reddit.com` host, `.json`/`.rss` suffixed or not)
    → the old.reddit `?limit=500&sort=top` thread form. Everything else
    (listings, search, subreddit roots) → its new-reddit canonical. Never emits
    `.json`. Short links (`redd.it/<id>`) are resolved by the handler *before*
    calling this — a bare short link classifies as `listing` here (no thread
    path to canonicalize).
    """
    parsed = urlparse(url)
    path = _strip_data_suffix(parsed.path or "/")
    match = _COMMENTS_RE.match(path)
    if match is None:
        # Non-thread (listing / search / subreddit root) → new-reddit canonical.
        # Preserve the query (search `q=`, listing `t=`); drop the fragment.
        return "listing", urlunparse(parsed._replace(scheme="https", netloc="www.reddit.com", path=path, fragment=""))
    return "thread", _to_old_reddit_thread(match)


def _to_old_reddit_thread(match: re.Match[str]) -> str:
    """Build the canonical old.reddit thread URL from a matched comments path."""
    sub, post_id, slug = match.group("sub"), match.group("id"), match.group("slug")
    path = f"/r/{sub}/comments/{post_id}/"
    if slug:
        path += f"{slug}/"
    query = urlencode({"limit": "500", "sort": "top"})
    return urlunparse(("https", "old.reddit.com", path, "", query, ""))


def _strip_data_suffix(path: str) -> str:
    """Drop a trailing `.json` / `.rss` (+ any trailing slash) from a path."""
    trimmed = path.rstrip("/")
    for suffix in (".json", ".rss"):
        if trimmed.endswith(suffix):
            return trimmed[: -len(suffix)]
    return path


# --------------------------------------------------------------------- #
# Parsed thread model
# --------------------------------------------------------------------- #


@dataclass(slots=True)
class RedditComment:
    """One old.reddit comment: author, score, markdown body, nesting depth."""

    author: str
    body_md: str
    depth: int
    score: int | None = None


@dataclass(slots=True)
class RedditThread:
    """A parsed old.reddit thread — the post plus a flat, depth-tagged comment list.

    `comment_total` is the authoritative oracle read off the post's `N comments`
    bylink (may exceed `len(comments)` on threads past the `?limit=500` ceiling).
    """

    title: str | None
    author: str | None
    body_md: str
    subreddit: str | None
    comments: list[RedditComment] = field(default_factory=list)
    score: int | None = None
    comment_total: int | None = None


# --------------------------------------------------------------------- #
# old.reddit HTML parsing
# --------------------------------------------------------------------- #


def parse_thread(html: str) -> RedditThread | None:
    """Parse old.reddit thread HTML into a `RedditThread`, or None if unparseable.

    Returns None when the DOM has neither a post `div.thing.link` nor any
    comment node — i.e. the parser's structural anchors are absent (old.reddit
    changed, or the page is not a thread). The caller treats None as a parse
    miss and falls through, never silently returning empty content.
    """
    tree = HTMLParser(html)
    op = tree.css_first("div.thing.link")
    comment_nodes = tree.css("div.thing.comment")
    if op is None and not comment_nodes:
        return None

    title = _first_text(op, "a.title") if op else None
    author = _first_text(op, "a.author") if op else None
    subreddit = _subreddit_from_op(op)
    body_md = _entry_body_md(op) if op else ""
    score = _int_attr(op, "data-score") if op else None
    comment_total = _comment_total(op) if op else None

    comments = [c for node in comment_nodes if (c := _parse_comment(node)) is not None]

    return RedditThread(
        title=title,
        author=author,
        body_md=body_md,
        subreddit=subreddit,
        comments=comments,
        score=score,
        comment_total=comment_total,
    )


def _parse_comment(node: Node) -> RedditComment | None:
    """Parse one `div.thing.comment` node into a `RedditComment`.

    Reads author/score/body from the comment's OWN `div.entry` (the nearest
    descendant in document order — nested replies live under `div.child`, a
    sibling of `entry`, so they never bleed in). Depth counts ancestor comment
    nodes. Returns None for a body-less shell (a `more comments` stub or a fully
    removed node with nothing to show).
    """
    entry = node.css_first("div.entry")
    if entry is None:
        return None
    body_md = _md_from(entry.css_first("div.usertext-body div.md"))
    if not body_md:
        return None
    author = _node_text(entry.css_first("a.author")) or "[deleted]"
    score = _comment_score(entry)
    return RedditComment(author=author, body_md=body_md, depth=_comment_depth(node), score=score)


def _comment_depth(node: Node) -> int:
    """Count how many `comment` ancestors wrap this node (top-level = 0)."""
    depth = 0
    parent = node.parent
    while parent is not None:
        classes = parent.attributes.get("class") or ""
        if "comment" in classes and "thing" in classes:
            depth += 1
        parent = parent.parent
    return depth


def _comment_score(entry: Node) -> int | None:
    """Read a comment's score from its `span.score.unvoted` (title attr or text).

    Returns None when the score is hidden (new/controversial comments render
    `score hidden`), never a fabricated 0.
    """
    span = entry.css_first("span.score.unvoted")
    if span is None:
        return None
    title = span.attributes.get("title")
    if title and title.strip().lstrip("-").isdigit():
        return int(title.strip())
    match = _COUNT_RE.search(span.text())
    return int(match.group(1).replace(",", "")) if match else None


def _comment_total(op: Node) -> int | None:
    """Read the authoritative comment total from the post's `N comments` bylink."""
    link = op.css_first("a.comments")
    if link is None:
        return None
    match = _COUNT_RE.search(link.text())
    return int(match.group(1).replace(",", "")) if match else None


def _entry_body_md(op: Node) -> str:
    """The OP self-text body (empty for link posts)."""
    return _md_from(op.css_first("div.entry div.usertext-body div.md"))


def _subreddit_from_op(op: Node | None) -> str | None:
    if op is None:
        return None
    sub = op.attributes.get("data-subreddit")
    if sub:
        return sub
    link = _first_text(op, "a.subreddit")
    return link.removeprefix("r/") if link else None


def _md_from(node: Node | None) -> str:
    """Convert a comment/post body node's inner HTML to markdown."""
    if node is None:
        return ""
    return to_markdown(node.html or "").strip()


# --------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------- #


def render_markdown(thread: RedditThread) -> str:
    """Render a parsed thread to markdown: post header + scored, nested comments.

    Comments are indented by nesting depth (blockquote per level) and tagged
    with `u/author` + score, so the structure the RSS path flattens away is
    preserved. This is the differentiator over RSS — a scored, ranked, nested
    sample rather than a flat recent list.
    """
    parts: list[str] = []
    if thread.title:
        parts.append(f"# {thread.title}\n")
    meta_bits: list[str] = []
    if thread.author:
        meta_bits.append(f"by u/{thread.author}")
    if thread.subreddit:
        meta_bits.append(f"in r/{thread.subreddit}")
    if thread.score is not None:
        meta_bits.append(f"{thread.score} points")
    if meta_bits:
        parts.append(" · ".join(meta_bits) + "\n")
    if thread.body_md:
        parts.append(thread.body_md + "\n")
    parts.append("---\n")

    total = thread.comment_total
    shown = len(thread.comments)
    header = f"## Comments ({shown} of {total})" if total is not None and total > shown else f"## Comments ({shown})"
    parts.append(header + "\n")
    parts.append("_Top-ranked sample from old.reddit, scored and nested._\n")
    for c in thread.comments:
        parts.append(_render_comment(c))

    return "\n".join(parts).strip() + "\n"


def _render_comment(c: RedditComment) -> str:
    """One comment as a depth-indented blockquote with a `u/author (score)` tag."""
    prefix = "> " * (c.depth + 1)
    score = f" ({c.score} points)" if c.score is not None else ""
    body = "\n".join(f"{prefix}{line}".rstrip() for line in c.body_md.splitlines())
    return f"{body}\n{prefix.rstrip()}\n{prefix}— u/{c.author}{score}\n"


def _first_text(root: Node, selector: str) -> str | None:
    return _node_text(root.css_first(selector))


def _node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    text = node.text(deep=True, strip=True)
    return text or None


def _int_attr(node: Node, attr: str) -> int | None:
    raw = node.attributes.get(attr)
    if raw and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    return None
