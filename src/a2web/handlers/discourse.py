"""Discourse handler — topics and forum indexes via the engine-wide .json API.

Discourse is one of the most widely deployed forum engines. Every Discourse
URL serves a JSON twin — `<forum>/latest.json` for the topic list, `<topic>.json`
for a topic's full post stream (with `reply_to_post_number` giving the reply
tree). One handler keyed on the Discourse JSON contract therefore covers every
Discourse forum at once.

Because Discourse runs on arbitrary domains, `matches()` claims a URL only
when its host is in the configured `AppSettings.discourse_hosts` allowlist.

The handler MUST NOT raise on routine HTTP failures; it translates errors and
non-Discourse responses to closed `Verdict` values.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from html_fragment import to_markdown, to_text
from http_fetch import fetch_bytes

from ..models import Heading, NextLink, Verdict
from ..settings import DEFAULT_DISCOURSE_HOSTS
from ._common import empty_result, map_non_ok

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult

_DEFAULT_TIMEOUT_S = 10
# A Discourse topic path: /t/<slug>/<id> or /t/<id>, with an optional
# trailing /<post_number> focus segment.
_TOPIC_PATH_RE = re.compile(r"^/t/(?:(?P<slug>[^/]+)/)?(?P<id>\d+)(?:/\d+)?/?$")
# Reply-tree recursion is capped so a pathological thread cannot blow the stack.
_MAX_DEPTH = 20
# Cap on rendered topic-list rows.
_MAX_TOPICS = 50


class DiscourseHandler:
    """Tier-0 handler for Discourse forums (config-allowlisted hosts)."""

    name: str = "site_handler:discourse"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        hosts = settings.discourse_hosts if settings is not None else list(DEFAULT_DISCOURSE_HOSTS)
        host = (urlparse(url).hostname or "").lower()
        return host in {h.lower() for h in hosts}

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import Rendered, TierResult

        parsed = urlparse(url)
        topic_match = _TOPIC_PATH_RE.match(parsed.path or "")
        if topic_match is not None:
            json_url = _topic_json_url(parsed.scheme, parsed.netloc, topic_match)
        else:
            json_url = urlunparse((parsed.scheme or "https", parsed.netloc, "/latest.json", "", "", ""))

        outcome = await fetch_bytes(
            json_url,
            headers={"User-Agent": state.settings.default_ua},
            timeout_s=_DEFAULT_TIMEOUT_S,
        )

        non_ok = map_non_ok(outcome, url=url)
        if non_ok is not None:
            return non_ok

        try:
            payload = json.loads(outcome.body)
        except (ValueError, json.JSONDecodeError):
            # A configured host that is not actually Discourse — fall through.
            return empty_result(url, Verdict.not_found)

        rendered = _render_topic(payload) if topic_match is not None else _render_index(payload, url)
        if rendered is None:
            # Valid JSON but not a Discourse topic / index — fall through.
            return empty_result(url, Verdict.not_found)

        return TierResult(
            body=outcome.body,
            content_type="application/json",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered.from_dict(rendered),
            next_links=list(rendered.get("next_links") or []),
            verdict=Verdict.ok,
        )


# --------------------------------------------------------------------- #
# JSON URL construction
# --------------------------------------------------------------------- #


def _topic_json_url(scheme: str, netloc: str, match: re.Match[str]) -> str:
    """Build the `<topic>.json` URL, dropping any trailing post-number focus."""
    slug = match.group("slug")
    topic_id = match.group("id")
    path = f"/t/{slug}/{topic_id}.json" if slug else f"/t/{topic_id}.json"
    return urlunparse((scheme or "https", netloc, path, "", "", ""))


# --------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------- #


def _render_topic(payload: Any) -> dict[str, Any] | None:
    """Render a Discourse topic's post stream, threaded via `reply_to_post_number`.

    Returns `None` when the payload is not a Discourse topic (no `post_stream`).
    """
    if not isinstance(payload, dict):
        return None
    post_stream = payload.get("post_stream")
    if not isinstance(post_stream, dict):
        return None
    raw_posts = post_stream.get("posts")
    if not isinstance(raw_posts, list):
        return None
    posts = [p for p in raw_posts if isinstance(p, dict) and isinstance(p.get("post_number"), int)]
    if not posts:
        return None
    posts.sort(key=lambda p: p["post_number"])
    op = posts[0]
    op_number = op["post_number"]
    by_number = {p["post_number"]: p for p in posts}

    # Build the reply forest. A post replying to nothing (or to the OP, or to
    # an absent post) hangs directly under the OP; otherwise under its parent.
    children: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for post in posts:
        number = post["post_number"]
        if number == op_number:
            continue
        rtpn = post.get("reply_to_post_number")
        parent = rtpn if isinstance(rtpn, int) and rtpn != number and rtpn in by_number else op_number
        children[parent].append(post)

    title = to_text(payload.get("fancy_title") or payload.get("title") or "") or None
    op_author = _post_author(op)

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    if op_author:
        parts.append(f"by {op_author}\n")
    op_body = to_markdown(op.get("cooked") or "")
    if op_body:
        parts.append(op_body + "\n")
    parts.append("---\n")
    parts.append("## Discussion\n")
    for child in children.get(op_number, []):
        parts.append(_render_post(child, children=children, depth=1))

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))
    headings.append(Heading(level=2, text="Discussion"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title,
        "byline": op_author,
        "headings": headings,
    }


def _render_post(post: dict[str, Any], *, children: dict[int, list[dict[str, Any]]], depth: int) -> str:
    """Render one post and its reply subtree, blockquote-indented by depth."""
    author = _post_author(post) or "[unknown]"
    body = to_markdown(post.get("cooked") or "")
    quote = ">" * depth
    if body:
        quoted = "\n".join(f"{quote} {line}".rstrip() for line in body.splitlines())
        block = f"{quoted}\n{quote}\n{quote} — {author}\n"
    else:
        block = f"{quote} _[post removed]_ — {author}\n"
    if depth < _MAX_DEPTH:
        number = post["post_number"]
        for child in children.get(number, []):
            block += _render_post(child, children=children, depth=depth + 1)
    return block


def _render_index(payload: Any, url: str) -> dict[str, Any] | None:
    """Render a Discourse forum index (`latest.json`) as a topic list.

    Returns `None` when the payload is not a Discourse index (no `topic_list`).
    """
    if not isinstance(payload, dict):
        return None
    topic_list = payload.get("topic_list")
    if not isinstance(topic_list, dict):
        return None
    topics = topic_list.get("topics")
    if not isinstance(topics, list) or not topics:
        return None
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    host = parsed.netloc

    parts: list[str] = ["# Discourse — latest topics\n"]
    next_links: list[NextLink] = []
    for topic in topics[:_MAX_TOPICS]:
        if not isinstance(topic, dict):
            continue
        title = to_text(topic.get("fancy_title") or topic.get("title") or "")
        topic_id = topic.get("id")
        if not title or not isinstance(topic_id, int):
            continue
        slug = topic.get("slug") or ""
        posts_count = topic.get("posts_count", 0) or 0
        reply_count = topic.get("reply_count", 0) or 0
        topic_url = f"{scheme}://{host}/t/{slug}/{topic_id}" if slug else f"{scheme}://{host}/t/{topic_id}"
        parts.append(f"- **{title}** ({posts_count} posts)\n  <{topic_url}>")
        next_links.append(
            NextLink(anchor=title, url=topic_url, reason=f"{reply_count} replies", kind="discussion"),
        )
    if not next_links:
        return None

    parts.insert(1, f"## Topics ({len(next_links)})\n")
    headings = [
        Heading(level=1, text="Discourse — latest topics"),
        Heading(level=2, text=f"Topics ({len(next_links)})"),
    ]
    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": "Discourse — latest topics",
        "byline": None,
        "headings": headings,
        "next_links": next_links,
    }


def _post_author(post: dict[str, Any]) -> str | None:
    """A post's author — the Discourse `username` (stable), `name` is optional."""
    username = post.get("username")
    return str(username) if username else None
