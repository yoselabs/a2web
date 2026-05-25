"""Habr handler — article + threaded comments via the kek/v2 JSON API.

Habr article pages are a Vue SPA: the article body is server-rendered (so
trafilatura recovers it) but the comment thread is client-rendered — the raw
HTML carries only `tm-placeholder` skeletons. A raw-tier fetch therefore loses
the entire discussion. Habr's internal `kek/v2` API returns both the article
and the full comment tree in two browser-free GETs:

  * `kek/v2/articles/<id>/`          — `titleHtml`, `textHtml`, `author`
  * `kek/v2/articles/<id>/comments/` — `comments` (id -> node), `threads` (roots)

The handler MUST NOT raise on routine HTTP failures; it translates errors to
closed `Verdict` values. A failed comments fetch degrades to article-only.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlparse

import anyio

from ..models import Heading, Verdict
from ..packages.html_fragment import to_markdown, to_text
from ..packages.http_fetch import FetchVerdict, fetch_bytes
from ._common import empty_result

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult

_DEFAULT_TIMEOUT_S = 10
_HABR_HOSTS = frozenset({"habr.com", "www.habr.com"})
# Habr article paths: optional /ru|/en language segment, then one of the
# article / company-article / legacy-post / legacy-company-blog forms, then
# the numeric article id.
_ARTICLE_PATH_RE = re.compile(
    r"^/(?:(?P<lang>ru|en)/)?"
    r"(?:companies/[^/]+/articles|company/[^/]+/blog|articles|post)/"
    r"(?P<id>\d+)/?$",
    re.IGNORECASE,
)
# Reply-tree recursion + total-comment caps — bound output on popular posts.
_MAX_DEPTH = 20
_MAX_COMMENTS = 400


def _parse(url: str) -> tuple[str, str] | None:
    """Return `(article_id, lang)` for a Habr article URL, else `None`.

    `lang` is `ru` or `en`; defaults to `ru` when the URL omits the segment.
    """
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _HABR_HOSTS:
        return None
    match = _ARTICLE_PATH_RE.match(parsed.path or "")
    if match is None:
        return None
    lang = (match.group("lang") or "ru").lower()
    return (match.group("id"), lang)


class HabrHandler:
    """Tier-0 handler for Habr articles (article body + threaded comments)."""

    name: str = "site_handler:habr"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        return _parse(url) is not None

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        del cookies  # handler manages its own transport
        from ..tiers import Rendered, TierResult

        parsed = _parse(url)
        if parsed is None:  # pragma: no cover - matches() gates this
            return empty_result(url, Verdict.not_found)
        article_id, lang = parsed
        base = f"https://habr.com/kek/v2/articles/{article_id}"
        params = {"fl": lang, "hl": lang}

        results: dict[str, dict[str, Any] | None] = {"article": None, "comments": None}
        request_headers = {"User-Agent": state.settings.default_ua}

        async def _load(key: str, endpoint: str) -> None:
            results[key] = await _fetch_json(endpoint, params, request_headers)

        async with anyio.create_task_group() as tg:
            tg.start_soon(_load, "article", f"{base}/")
            tg.start_soon(_load, "comments", f"{base}/comments/")

        article = results["article"]
        if not isinstance(article, dict) or not article.get("textHtml"):
            # Non-200, malformed JSON, or an error payload for an unknown id.
            return empty_result(url, Verdict.not_found)

        comments = results["comments"]
        rendered = _render_article(article, comments if isinstance(comments, dict) else None)

        return TierResult(
            body=b"",
            content_type="application/json",
            status_code=200,
            final_url=url,
            pre_rendered=Rendered.from_dict(rendered),
            verdict=Verdict.ok,
        )


async def _fetch_json(endpoint: str, params: dict[str, str], headers: dict[str, str]) -> dict[str, Any] | None:
    """GET `endpoint?params` via the shared primitive and return parsed JSON,
    or `None` on any routine failure.

    Never raises — a per-task failure must not cancel its sibling in the task
    group, so each fetch isolates its own errors.
    """
    url = f"{endpoint}?{urlencode(params)}" if params else endpoint
    outcome = await fetch_bytes(url, headers=headers, timeout_s=_DEFAULT_TIMEOUT_S)
    if outcome.verdict is not FetchVerdict.ok or outcome.status_code != 200:
        return None
    try:
        payload = json.loads(outcome.body)
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


# --------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------- #


def _render_article(article: dict[str, Any], comments: dict[str, Any] | None) -> dict[str, Any]:
    """Render the article body and, when available, a threaded discussion."""
    title = to_text(article.get("titleHtml") or "") or None
    author = article.get("author")
    byline = None
    if isinstance(author, dict) and author.get("alias"):
        byline = str(author["alias"])
    body = to_markdown(article.get("textHtml") or "")

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

    discussion = _render_discussion(comments) if comments is not None else ""
    if discussion:
        parts.append("---\n")
        parts.append("## Discussion\n")
        parts.append(discussion)
        headings.append(Heading(level=2, text="Discussion"))

    return {
        "content_md": "\n".join(parts).strip() + "\n",
        "title": title,
        "byline": byline,
        "headings": headings,
    }


def _render_discussion(comments_payload: dict[str, Any]) -> str:
    """Render the comment tree threaded — `None`/empty inputs yield `""`."""
    comments = comments_payload.get("comments")
    threads = comments_payload.get("threads")
    if not isinstance(comments, dict) or not comments or not isinstance(threads, list):
        return ""

    children: dict[str, list[str]] = defaultdict(list)
    for cid, node in comments.items():
        if not isinstance(node, dict):
            continue
        parent_id = node.get("parentId")
        if parent_id is not None and str(parent_id) in comments:
            children[str(parent_id)].append(str(cid))

    budget = [_MAX_COMMENTS]
    blocks: list[str] = []
    for root_id in threads:
        block = _render_comment(str(root_id), comments, children, depth=1, budget=budget)
        if block:
            blocks.append(block)
    return "\n".join(blocks)


def _render_comment(
    comment_id: str,
    comments: dict[str, Any],
    children: dict[str, list[str]],
    *,
    depth: int,
    budget: list[int],
) -> str:
    """Render one comment and its reply subtree, blockquote-indented by depth."""
    node = comments.get(comment_id)
    if not isinstance(node, dict) or budget[0] <= 0:
        return ""
    budget[0] -= 1

    author = "[unknown]"
    raw_author = node.get("author")
    if isinstance(raw_author, dict) and raw_author.get("alias"):
        author = str(raw_author["alias"])
    body = to_markdown(node.get("message") or "")
    quote = ">" * depth
    if body:
        quoted = "\n".join(f"{quote} {line}".rstrip() for line in body.splitlines())
        block = f"{quoted}\n{quote}\n{quote} — {author}\n"
    else:
        block = f"{quote} _[comment removed]_ — {author}\n"

    if depth < _MAX_DEPTH:
        for child_id in children.get(comment_id, []):
            block += _render_comment(child_id, comments, children, depth=depth + 1, budget=budget)
    return block
