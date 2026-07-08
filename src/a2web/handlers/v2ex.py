"""V2EX handler — topic + replies via the open API v1.

V2EX serves anonymous scrapers a stripped HTML page (a topic came back as a
~275-char shell in the probe), but its API v1 is open and unauthenticated:

  * `api/topics/show.json?id=<id>`         — `list[1]`, the topic
  * `api/replies/show.json?topic_id=<id>`  — a flat array of replies

V2EX replies are linear — there is no parent/child reply structure — so the
discussion renders as a flat, chronologically ordered list.

The handler MUST NOT raise on routine HTTP failures; it translates errors to
closed `Verdict` values. A failed replies fetch degrades to topic-only.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import anyio
from html_fragment import to_markdown
from http_fetch import FetchVerdict, fetch_bytes

from ..models import Heading, Verdict
from ._common import empty_result

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult

_DEFAULT_TIMEOUT_S = 10
_V2EX_HOSTS = frozenset({"v2ex.com", "www.v2ex.com"})
# A V2EX topic path: /t/<id>, with an optional trailing slug.
_TOPIC_PATH_RE = re.compile(r"^/t/(?P<id>\d+)(?:/.*)?$")
_API_BASE = "https://www.v2ex.com/api"
# Bound output on heavily-replied topics.
_MAX_REPLIES = 200


def _topic_id(url: str) -> str | None:
    """Return the numeric topic id for a V2EX topic URL, else `None`."""
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _V2EX_HOSTS:
        return None
    match = _TOPIC_PATH_RE.match(parsed.path or "")
    return match.group("id") if match is not None else None


class V2EXHandler:
    """Tier-0 handler for V2EX topics (topic body + linear replies)."""

    name: str = "site_handler:v2ex"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        return _topic_id(url) is not None

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import Rendered, TierResult

        topic_id = _topic_id(url)
        if topic_id is None:  # pragma: no cover - matches() gates this
            return empty_result(url, Verdict.not_found)

        results: dict[str, Any] = {"topic": None, "replies": None}
        request_headers = {"User-Agent": state.settings.default_ua}

        async def _load(key: str, endpoint: str) -> None:
            results[key] = await _fetch_json(endpoint, request_headers)

        async with anyio.create_task_group() as tg:
            tg.start_soon(_load, "topic", f"{_API_BASE}/topics/show.json?id={topic_id}")
            tg.start_soon(_load, "replies", f"{_API_BASE}/replies/show.json?topic_id={topic_id}")

        topic_list = results["topic"]
        if not isinstance(topic_list, list) or not topic_list or not isinstance(topic_list[0], dict):
            # Non-200, malformed JSON, or an empty list for an unknown id.
            return empty_result(url, Verdict.not_found)

        raw_replies = results["replies"]
        replies = raw_replies if isinstance(raw_replies, list) else []
        rendered = _render(topic_list[0], replies)

        return TierResult(
            body=b"",
            content_type="application/json",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
        )


async def _fetch_json(endpoint: str, headers: dict[str, str]) -> Any:
    """GET `endpoint` via the shared primitive and return parsed JSON, or
    `None` on any routine failure.

    Never raises — a per-task failure must not cancel its sibling in the task
    group, so each fetch isolates its own errors.
    """
    outcome = await fetch_bytes(endpoint, headers=headers, timeout_s=_DEFAULT_TIMEOUT_S)
    if outcome.verdict is not FetchVerdict.ok or outcome.status_code != 200:
        return None
    try:
        return json.loads(outcome.body)
    except (ValueError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------- #


def _render(topic: dict[str, Any], replies: list[Any]) -> dict[str, Any]:
    """Render a V2EX topic body and its linear replies to markdown."""
    title = (topic.get("title") or "").strip() or None
    byline = _member_name(topic.get("member"))
    body = _post_body(topic)

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    if byline:
        parts.append(f"by {byline}\n")
    if body:
        parts.append(body + "\n")

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))

    reply_dicts = [r for r in replies if isinstance(r, dict)][:_MAX_REPLIES]
    if reply_dicts:
        parts.append("---\n")
        parts.append(f"## Replies ({len(reply_dicts)})\n")
        for reply in reply_dicts:
            author = _member_name(reply.get("member")) or "[unknown]"
            reply_body = _post_body(reply)
            parts.append(f"**{author}:**\n\n{reply_body}\n" if reply_body else f"**{author}:** _[empty]_\n")
        headings.append(Heading(level=2, text="Replies"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title,
        "byline": byline,
        "headings": headings,
    }


def _member_name(member: Any) -> str | None:
    """A V2EX member's username, or `None`."""
    if isinstance(member, dict) and member.get("username"):
        return str(member["username"])
    return None


def _post_body(post: dict[str, Any]) -> str:
    """A topic / reply body — `content` is raw markdown; fall back to the
    rendered HTML only when `content` is empty."""
    content = (post.get("content") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if content:
        return content
    return to_markdown(post.get("content_rendered") or "")
