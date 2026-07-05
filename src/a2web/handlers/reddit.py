"""Reddit handler — projects Reddit URL shapes onto keyless `.rss` (Atom) feeds.

Reddit's `.json` (and HTML, and `oauth`) endpoints sit behind a network-policy
wall on non-browser clients — Reddit's own `server: snooserv` "whoa there,
pardner" 403, NOT Datadome. Measured live (see ADR-0011): every HTTP-client
path is blocked byte-identically with vs without logged-in cookies, and even a
commercial smart-proxy (Zyte) is banned on `.json`. The `.rss` (Atom) feeds are
served by a different, non-API-gated channel and are NOT walled — they serve
keyless and live from datacenter/remote IPs. So this handler rewrites every
claimed shape to its `.rss` equivalent and parses the Atom with stdlib
`xml.etree.ElementTree`. It MUST NOT fall back to `.json` (ADR-0011 rule 2).

Covered shapes:

  * `/r/<sub>/search/?q=...`                    → `/r/<sub>/search.rss?q=...`
  * `/r/<sub>/` (bare / hot), `/r/<sub>/top` …  → `/r/<sub>/.rss`, `/r/<sub>/top.rss`
  * `/r/<sub>/comments/<id>/<slug>/`            → `/r/<sub>/comments/<id>/<slug>/.rss`
  * `/r/<sub>/comments/<id>/<slug>/<comment>/`  → thread `.rss` (flat, un-focused)
  * `redd.it/<id>`                              → short URL, HEAD-resolved then recursed

**RSS is a DEGRADED projection, by design.** Comments come back FLAT (no
nesting), RECENT-ordered, capped at whatever the feed carries (~25-30), with
NO scores and NO `more` stubs. Search/listing stubs carry NO score or
comment count (the feed simply omits them). The rendered output SURFACES this
as a sample — it never implies a complete or top-ranked set. Permalink focus
is lost (a comment permalink renders as the whole flat thread).

The handler MUST NOT raise on routine HTTP failures; it translates errors to
closed `Verdict` values. A terminal wall on a Reddit surface emits the
critical `try_user_browser` operator hint EAGERLY (the never-silently-miss
tenet): Reddit shapes the handler does not claim fall through to raw/jina and
pick up the same hint from the orchestrator's late seam.
"""

from __future__ import annotations

import re
import time as _time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import anyio

from .. import content_expectations
from ..models import Heading, NextLink, OperatorHint, Verdict, comments_partial_hint, try_user_browser_hint
from ..packages.html_fragment import to_markdown
from ..packages.http_fetch import FetchVerdict, fetch_bytes
from . import _reddit_html as rh
from ._common import empty_result

if TYPE_CHECKING:
    from ..settings import AppSettings
    from ..state import AppState
    from ..tiers import TierResult


# --------------------------------------------------------------------- #
# URL shape detection
# --------------------------------------------------------------------- #

# Captures everything: /r/<sub>/comments/<id> with an optional /slug/ and
# an optional /<comment_id>/ (permalink to a specific comment).
_COMMENTS_PATH_RE = re.compile(r"^/r/[^/]+/comments/[^/]+(/|$)")
_PERMALINK_PATH_RE = re.compile(r"^/r/(?P<sub>[^/]+)/comments/(?P<post>[^/]+)/(?P<slug>[^/]+)/(?P<comment>[a-z0-9]+)/?$")
# Search paths: `/r/<sub>/search/` (subreddit-scoped) or `/search/` (site-wide).
_SEARCH_PATH_RE = re.compile(r"^(/r/[^/]+)?/search/?$")
# Listing paths: subreddit root or a sort suffix.
_LISTING_PATH_RE = re.compile(r"^/r/(?P<sub>[^/]+)(?:/(?P<sort>top|hot|new|rising|best|controversial))?/?$")
# Sorts that map to an explicit `/r/<sub>/<sort>.rss` feed. `hot`/`best` and
# the bare subreddit all map to the default `/r/<sub>/.rss` feed.
_RSS_SORTS = frozenset({"top", "new", "rising", "controversial"})
_REDDIT_HOSTS = frozenset({"reddit.com", "www.reddit.com", "old.reddit.com", "np.reddit.com"})
_SHORT_HOSTS = frozenset({"redd.it"})
_DEFAULT_TIMEOUT_S = 10
# Bounded backoff for RSS 429s. Retries are attempted between these sleeps;
# on exhaustion the handler fails loud (never a silent empty). Tests patch
# this to `()` to disable sleeping.
_RSS_BACKOFF_S: tuple[float, ...] = (0.5, 1.5)
# Atom namespace stdlib ElementTree prepends to every tag.
_A = "{http://www.w3.org/2005/Atom}"

_UrlShape = Literal["comments", "permalink", "search", "listing"]


def _url_shape(url: str) -> _UrlShape | None:
    """Classify a Reddit URL into one of the handled shapes."""
    parsed = urlparse(url)
    path = parsed.path or ""
    if _SEARCH_PATH_RE.match(path):
        return "search"
    if _COMMENTS_PATH_RE.match(path):
        return "permalink" if _detect_permalink(url) else "comments"
    if _LISTING_PATH_RE.match(path):
        return "listing"
    return None


def _is_reddit_host(host: str) -> bool:
    return host in _REDDIT_HOSTS


def _is_short_host(host: str) -> bool:
    return host in _SHORT_HOSTS


def _detect_permalink(url: str) -> str | None:
    """Return the focused-comment ID if `url` is a permalink, else None.

    Reddit permalinks look like `/r/X/comments/Y/slug/Z/` where `Z` is a
    base36 comment id. A bare thread URL `/r/X/comments/Y/slug/` has the
    slug as its trailing segment and is NOT a permalink.

    RSS cannot render a focused permalink view (the feed is flat), so the
    handler routes permalinks to the whole thread `.rss` — but classifying
    the shape still lets the caller know a specific comment was requested.
    """
    parsed = urlparse(url)
    match = _PERMALINK_PATH_RE.match(parsed.path or "")
    if not match:
        return None
    candidate = match.group("comment")
    if "_" in candidate or len(candidate) > 12:
        return None
    return candidate


# --------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------- #


class RedditHandler:
    """Site handler for Reddit search, listings, threads, and short URLs."""

    name: str = "site_handler:reddit"

    def matches(self, url: str, settings: AppSettings | None = None) -> bool:
        del settings
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if _is_short_host(host):
            return True
        if not _is_reddit_host(host):
            return False
        path = parsed.path or ""
        return bool(_COMMENTS_PATH_RE.match(path) or _SEARCH_PATH_RE.match(path) or _LISTING_PATH_RE.match(path))

    async def fetch(self, url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
        from ..tiers import Rendered, TierResult

        parsed = urlparse(url)
        if _is_short_host(parsed.hostname or ""):
            resolved = await _resolve_short_url(url, state=state)
            if resolved is None:
                return empty_result(url, Verdict.connection_error)
            resolved_parsed = urlparse(resolved)
            if _is_reddit_host(resolved_parsed.hostname or "") and _COMMENTS_PATH_RE.match(resolved_parsed.path or ""):
                return await self.fetch(resolved, state=state, cookies=cookies)
            return TierResult(
                body=b"",
                content_type="",
                status_code=0,
                final_url=resolved,
                no_match=True,
                verdict=Verdict.other,
            )

        shape = _url_shape(url)
        if shape is None:  # defensive — matches() only claims the shapes above
            return empty_result(url, Verdict.other)

        # Eager paid routing (reddit-via-zyte): a thread + a configured Zyte tier
        # under the robustness policy fetches old.reddit `?limit=500` directly —
        # a scored, nested, ~top-500 comment sample — bypassing the doomed free
        # ladder (raw/jina all lose on Reddit). A transient miss or unparseable
        # page returns None here and falls through to the keyless RSS channel;
        # a bad Zyte key fails loud (never a silent downgrade).
        if shape in ("comments", "permalink") and _zyte_reddit_enabled(state):
            zyte_result = await _fetch_via_zyte_oldreddit(url, state=state)
            if zyte_result is not None:
                return zyte_result

        rss_url = _to_rss_url(url, shape)
        outcome = await _fetch_rss(rss_url, state=state, cookies=cookies)

        if outcome.verdict is FetchVerdict.timeout:
            return empty_result(url, Verdict.timeout)
        if outcome.verdict is FetchVerdict.rate_limited or outcome.status_code == 429:
            # Retries exhausted (see `_fetch_rss`). Fail loud — never a silent
            # empty. A `rate_limited` verdict surfaces in the narrative.
            return empty_result(url, Verdict.rate_limited)
        if outcome.verdict is FetchVerdict.not_found:
            if shape in ("search", "listing"):
                return empty_result(url, Verdict.not_found)
            return await _fetch_old_reddit_or_archive_signal(url, state=state, cookies=cookies)
        if outcome.status_code == 403:
            if shape in ("search", "listing"):
                # A 403 on Reddit's RSS search/listing surface is a wall (Reddit
                # rate-limits/blocks the keyless RSS). The archive tier can't
                # cache these dynamic pages — but the paid render (Zyte
                # browserHtml) reads them fine. Escalate to a direct site render;
                # if no paid tier is keyed, the orchestrator falls through to the
                # never-silently-miss hint (fail loud). Not authoritative.
                return _render_escalation_signal(url)
            # Thread 403 (quarantined / NSFW-unauth / private) — Wayback often
            # has a public capture from before the gate dropped.
            return _archive_escalation_signal(
                url,
                reason="reddit_forbidden_try_archive",
                message="Reddit returned 403 (quarantined/NSFW/private); try archive snapshot.",
            )
        if outcome.verdict is not FetchVerdict.ok:
            return empty_result(url, Verdict.connection_error)

        feed = _parse_atom(outcome.body)
        if feed is None:
            return empty_result(url, Verdict.content_type_mismatch)

        if shape == "search":
            query = (parse_qs(parsed.query).get("q") or [""])[0]
            rendered = _render_search_atom(feed, query=query)
        elif shape == "listing":
            listing_match = _LISTING_PATH_RE.match(parsed.path or "")
            sub = listing_match.group("sub") if listing_match else "?"
            sort = (listing_match.group("sort") if listing_match else None) or "hot"
            time_window = (parse_qs(parsed.query).get("t") or [""])[0]
            rendered = _render_listing_atom(feed, subreddit=sub, sort=sort, time_window=time_window)
        else:
            rendered = _render_thread_atom(feed)

        if rendered.is_empty:
            if shape in ("search", "listing"):
                return empty_result(url, Verdict.not_found)
            return await _fetch_old_reddit_or_archive_signal(url, state=state, cookies=cookies)

        return TierResult(
            body=outcome.body,
            content_type="application/atom+xml",
            status_code=outcome.status_code,
            final_url=url,
            headers=outcome.headers,
            pre_rendered=Rendered(
                content_md=rendered.content_md,
                title=rendered.title,
                byline=rendered.byline,
                headings=rendered.headings,
            ),
            next_links=list(rendered.next_links),
            verdict=Verdict.ok,
        )


# --------------------------------------------------------------------- #
# RSS URL construction + fetch
# --------------------------------------------------------------------- #


def _to_rss_url(url: str, shape: _UrlShape) -> str:
    """Rewrite a Reddit URL to its keyless `.rss` (Atom) equivalent.

    Search/listing feeds append `.rss` to the last path segment
    (`search.rss`, `top.rss`); the bare subreddit and thread feeds append
    `/.rss` to the directory path (`/r/x/.rss`, `/r/x/comments/id/slug/.rss`).
    Only the query keys the feed honours are preserved.
    """
    parsed = urlparse(url)
    path = parsed.path or "/"
    query = parse_qs(parsed.query)

    if shape == "search":
        rss_path = path.rstrip("/") + ".rss"
        keep = {k: query[k] for k in ("q", "restrict_sr", "sort", "t") if k in query}
        new_query = urlencode(keep, doseq=True)
    elif shape == "listing":
        match = _LISTING_PATH_RE.match(path)
        sub = match.group("sub") if match else ""
        sort = (match.group("sort") if match else None) or "hot"
        if sort in _RSS_SORTS:
            rss_path = f"/r/{sub}/{sort}.rss"
            keep = {k: query[k] for k in ("t",) if k in query}
            new_query = urlencode(keep, doseq=True)
        else:  # bare / hot / best → the default feed
            rss_path = f"/r/{sub}/.rss"
            new_query = ""
    else:  # comments / permalink
        rss_path = path.rstrip("/") + "/.rss"
        new_query = ""

    return urlunparse(parsed._replace(netloc="www.reddit.com", path=rss_path, query=new_query))


async def _fetch_rss(rss_url: str, *, state: AppState, cookies: dict[str, str] | None):  # type: ignore[no-untyped-def]
    """Fetch an RSS feed with bounded backoff on 429.

    Reddit throttles bursts of RSS hits with `429`. This retries after each
    `_RSS_BACKOFF_S` sleep; on exhaustion it returns the last (still
    rate-limited) outcome so the caller fails loud. Response caching is the
    orchestrator's `http_cache` responsibility, one layer up.
    """
    last = None
    for backoff in (0.0, *_RSS_BACKOFF_S):
        if backoff:
            await anyio.sleep(backoff)
        outcome = await fetch_bytes(
            rss_url,
            headers={"User-Agent": state.settings.default_ua},
            timeout_s=_DEFAULT_TIMEOUT_S,
            cookies=cookies,
        )
        last = outcome
        rate_limited = outcome.verdict is FetchVerdict.rate_limited or outcome.status_code == 429
        if not rate_limited:
            return outcome
    return last


# --------------------------------------------------------------------- #
# Atom parsing
# --------------------------------------------------------------------- #


class _AtomEntry:
    """One parsed Atom `<entry>` — a Reddit post (t3) or comment (t1)."""

    __slots__ = ("author", "content_html", "epoch", "kind", "link", "reddit_id", "title")

    def __init__(
        self,
        *,
        kind: str,
        reddit_id: str,
        title: str | None,
        author: str | None,
        link: str | None,
        epoch: float | None,
        content_html: str | None,
    ) -> None:
        self.kind = kind
        self.reddit_id = reddit_id
        self.title = title
        self.author = author
        self.link = link
        self.epoch = epoch
        self.content_html = content_html


class _AtomFeed:
    """A parsed Atom feed: title/subtitle + ordered entries."""

    __slots__ = ("entries", "subtitle", "title")

    def __init__(self, *, title: str | None, subtitle: str | None, entries: list[_AtomEntry]) -> None:
        self.title = title
        self.subtitle = subtitle
        self.entries = entries


def _parse_atom(body: bytes) -> _AtomFeed | None:
    """Parse Reddit Atom bytes into an `_AtomFeed`, or None on malformed XML.

    Inline (not `to_thread`): Reddit feeds are tens of KB and parse in a few
    ms of pure CPU — no blocking I/O.
    """
    try:
        root = ET.fromstring(body)  # noqa: S314 — Reddit-served, no external entities
    except ET.ParseError:
        return None

    entries: list[_AtomEntry] = []
    for el in root.findall(f"{_A}entry"):
        reddit_id = _el_text(el.find(f"{_A}id")) or ""
        kind = reddit_id.split("_", 1)[0] if "_" in reddit_id else ""
        author = _strip_user_prefix(_el_text(el.find(f"{_A}author/{_A}name")))
        link_el = el.find(f"{_A}link")
        link = link_el.get("href") if link_el is not None else None
        entries.append(
            _AtomEntry(
                kind=kind,
                reddit_id=reddit_id,
                title=_el_text(el.find(f"{_A}title")),
                author=author,
                link=link,
                epoch=_iso_to_epoch(_el_text(el.find(f"{_A}published")) or _el_text(el.find(f"{_A}updated"))),
                content_html=_el_text(el.find(f"{_A}content")),
            ),
        )
    return _AtomFeed(
        title=_el_text(root.find(f"{_A}title")),
        subtitle=_el_text(root.find(f"{_A}subtitle")),
        entries=entries,
    )


def _el_text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    stripped = el.text.strip()
    return stripped or None


def _strip_user_prefix(name: str | None) -> str | None:
    """`/u/alice` → `alice`; `u/alice` → `alice`; None passes through."""
    if not name:
        return None
    return name.removeprefix("/u/").removeprefix("u/").strip() or None


def _iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _sub_from_link(link: str | None) -> str | None:
    """Extract the subreddit from a `.../r/<sub>/...` permalink."""
    if not link:
        return None
    match = re.search(r"/r/([^/]+)/", link)
    return match.group(1) if match else None


def _atom_body_markdown(content_html: str | None) -> str:
    """Convert a Reddit Atom `<content>` HTML body to markdown.

    Drops the `submitted by … [link] [comments]` footer that Reddit appends
    to post (t3) entries — everything after the `<!-- SC_ON -->` marker — so
    only the authored body survives. Comment (t1) entries have no footer, so
    the split is a no-op for them.
    """
    if not content_html:
        return ""
    head = content_html.split("<!-- SC_ON -->", 1)[0]
    head = re.sub(r"<!--.*?-->", "", head, flags=re.DOTALL)  # drop SC_OFF / SC_ON markers
    # Reddit wraps the authored body in `<div class="md">`; the OP entry also
    # carries a thumbnail `<table>` outside it. Extract just the md div so the
    # thumbnail/image noise never reaches the markdown. Reddit's rendered md
    # never nests `<div>`, so the greedy match closes on the md div itself.
    match = re.search(r'<div class="md">(.*)</div>', head, re.DOTALL)
    fragment = match.group(1) if match else head
    return to_markdown(fragment).strip()


# --------------------------------------------------------------------- #
# Rendering — a normalized `_RenderResult`, one per shape
# --------------------------------------------------------------------- #


class _RenderResult:
    """A rendered handler payload, shared by every shape."""

    __slots__ = ("byline", "content_md", "headings", "is_empty", "next_links", "title")

    def __init__(
        self,
        *,
        content_md: str = "",
        title: str | None = None,
        byline: str | None = None,
        headings: list[Heading] | None = None,
        next_links: list[NextLink] | None = None,
        is_empty: bool = False,
    ) -> None:
        self.content_md = content_md
        self.title = title
        self.byline = byline
        self.headings = headings or []
        self.next_links = next_links or []
        self.is_empty = is_empty


def _empty_render() -> _RenderResult:
    return _RenderResult(is_empty=True)


def _stub_line(*, title: str, subreddit: str | None, author: str | None, epoch: float | None, link: str | None, now: float) -> str:
    """One post-stub markdown line for search/listing renders.

    RSS carries no score or comment count, so the meta line is
    subreddit · author · age only — never a fabricated count.
    """
    meta_bits: list[str] = []
    if subreddit:
        meta_bits.append(f"r/{subreddit}")
    if author:
        meta_bits.append(f"u/{author}")
    if epoch is not None:
        meta_bits.append(human_age(now - epoch))
    meta = " · ".join(meta_bits)
    head = f"- **{title}** ({meta})" if meta else f"- **{title}**"
    return f"{head}\n  <{link}>" if link else head


def _post_entries(feed: _AtomFeed) -> list[_AtomEntry]:
    """t3 (post) entries with a title and permalink, cap 25 (feed page size)."""
    return [e for e in feed.entries if e.kind == "t3" and e.title][:25]


def _render_search_atom(feed: _AtomFeed, *, query: str) -> _RenderResult:
    """Render a search `.rss` feed to a terse markdown result list."""
    entries = _post_entries(feed)
    if not entries:
        return _empty_render()
    title_text = f"Search: {query}" if query else "Search"
    now = _time.time()
    lines = [
        _stub_line(
            title=(e.title or "").strip(),
            subreddit=_sub_from_link(e.link),
            author=e.author,
            epoch=e.epoch,
            link=e.link,
            now=now,
        )
        for e in entries
    ]
    parts = [f"# {title_text}\n", f"## Results ({len(lines)})\n", *lines]
    headings = [Heading(level=1, text=title_text), Heading(level=2, text=f"Results ({len(lines)})")]
    return _RenderResult(content_md="\n".join(parts).strip() + "\n", title=title_text, headings=headings)


def _render_listing_atom(feed: _AtomFeed, *, subreddit: str, sort: str, time_window: str) -> _RenderResult:
    """Render a subreddit listing `.rss` feed to a terse markdown list.

    NSFW filtering is dropped: the Atom feed carries no clean `over_18`
    signal (unlike the `.json` shape), so `next_links` are not SFW-filtered.
    """
    entries = _post_entries(feed)
    if not entries:
        return _empty_render()
    suffix = f" · {time_window}" if time_window and sort in ("top", "controversial") else ""
    title_text = f"r/{subreddit} · {sort}{suffix}"
    now = _time.time()
    lines = [
        _stub_line(
            title=(e.title or "").strip(),
            subreddit=None,  # the whole listing is one subreddit — named in the H1
            author=e.author,
            epoch=e.epoch,
            link=e.link,
            now=now,
        )
        for e in entries
    ]
    parts = [f"# {title_text}\n", f"## Posts ({len(lines)})\n", *lines]
    headings = [Heading(level=1, text=title_text), Heading(level=2, text=f"Posts ({len(lines)})")]
    next_links = [
        NextLink(anchor=(e.title or "").strip(), url=e.link, reason=human_age(now - e.epoch) if e.epoch else "", kind="drilldown")
        for e in entries[:10]
        if e.link and e.title
    ]
    return _RenderResult(content_md="\n".join(parts).strip() + "\n", title=title_text, headings=headings, next_links=next_links)


def _render_thread_atom(feed: _AtomFeed) -> _RenderResult:
    """Render a thread `.rss` feed: OP header + a FLAT comment sample.

    The Atom feed is entry[0] = the post (t3), entries[1:] = comments (t1),
    flat and recent-ordered. This loses nesting, scores, `more` stubs, and
    permalink focus versus the `.json` shape — the render SURFACES the loss
    as an explicit sample note so downstream never treats it as complete.
    """
    op = next((e for e in feed.entries if e.kind == "t3"), None)
    comments = [e for e in feed.entries if e.kind == "t1"]

    # Empty when there is no post entry AND no comment entries — a feed-level
    # `<title>` alone is not content (a deleted/empty thread still carries one).
    if op is None and not comments:
        return _empty_render()

    title = (op.title or "").strip() if op and op.title else _title_from_feed(feed)
    subreddit = _sub_from_link(op.link) if op else None
    author = op.author if op else None
    byline = f"u/{author}" if author else None
    body_md = _atom_body_markdown(op.content_html) if op else ""

    if title is None and not body_md and not comments:
        return _empty_render()

    parts: list[str] = []
    if title:
        parts.append(f"# {title}\n")
    meta_bits: list[str] = []
    if byline:
        meta_bits.append(f"by {byline}")
    if subreddit:
        meta_bits.append(f"in r/{subreddit}")
    if meta_bits:
        parts.append(" ".join(meta_bits) + "\n")
    if op and op.link:
        parts.append(f"<{op.link}>\n")
    if body_md:
        parts.append(body_md + "\n")
    parts.append("---\n")

    parts.append(f"## Comments (sample of {len(comments)})\n")
    parts.append("_Flat, most-recent sample from the RSS feed — not scored, not ranked, not complete._\n")
    for c in comments:
        c_body = _atom_body_markdown(c.content_html)
        if not c_body:
            continue
        c_author = c.author or "[deleted]"
        quoted = "\n".join(f"> {line}".rstrip() for line in c_body.splitlines())
        parts.append(f"{quoted}\n>\n> — u/{c_author}\n")

    headings = [h for h in (Heading(level=1, text=title) if title else None,) if h is not None]
    headings.append(Heading(level=2, text="Comments"))
    return _RenderResult(content_md="\n".join(parts).strip() + "\n", title=title, byline=byline, headings=headings)


def _title_from_feed(feed: _AtomFeed) -> str | None:
    """Reddit thread feed title is `<post title> : <subreddit>` — take the head."""
    if not feed.title:
        return None
    return feed.title.rsplit(" : ", 1)[0].strip() or None


def human_age(seconds_ago: float) -> str:
    """Compact age string: '3d', '2y', '5h', '12m', '45s'. Negative → '0s'."""
    s = max(0.0, float(seconds_ago))
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s // 60)}m"
    if s < 86400:
        return f"{int(s // 3600)}h"
    if s < 86400 * 365:
        return f"{int(s // 86400)}d"
    return f"{int(s // (86400 * 365))}y"


# --------------------------------------------------------------------- #
# Fail-loud signals + archive/old.reddit fallbacks
# --------------------------------------------------------------------- #


def _walled_signal(url: str) -> TierResult:
    """Terminal wall on a Reddit surface → fail loud with the eager browser hint.

    Carries `Verdict.block_page_detected` so the envelope's
    `retrieval_incomplete` flag is set, and the critical `try_user_browser`
    operator hint so the caller is told — imperatively — that the URL was NOT
    retrieved (never-silently-miss tenet).
    """
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=Verdict.block_page_detected,
        operator_hint=try_user_browser_hint(url),
    )


def _archive_escalation_signal(url: str, *, reason: str, message: str) -> TierResult:
    """Return a TierResult that asks the playbook to dispatch the archive tier."""
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=Verdict.not_found,
        operator_hint=OperatorHint(code=reason, message=message),
    )


def _render_escalation_signal(url: str) -> TierResult:
    """Ask the orchestrator to render this walled surface via the paid tier.

    Reddit's RSS search/listing 403s under rate-limiting, but Zyte `browserHtml`
    reads the same page fine. Carries `escalate_to_render` (not the eager
    `try_user_browser` hint) so the render is tried before any wall is declared;
    if no paid tier is keyed, the orchestrator's never-silently-miss hint fires.
    Non-authoritative `block_page_detected` so it never ends the run on its own.
    """
    from ..tiers import TierResult

    return TierResult(
        body=b"",
        content_type="",
        status_code=0,
        final_url=url,
        verdict=Verdict.block_page_detected,
        escalate_to_render=True,
    )


def _to_old_reddit_url(url: str) -> str:
    """Rewrite a reddit URL to old.reddit.com, dropping any .json/.rss suffix."""
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/")
    for suffix in (".json", ".rss"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    return urlunparse(parsed._replace(netloc="old.reddit.com", path=path, query=""))


# --------------------------------------------------------------------- #
# Eager paid (Zyte) old.reddit path (reddit-via-zyte)
# --------------------------------------------------------------------- #


def _zyte_reddit_enabled(state: AppState) -> bool:
    """True when Reddit threads should route eagerly to Zyte.

    Availability-gated ladder (design §5): requires a keyed Zyte tier AND the
    `robustness` policy. The `privacy` policy keeps Reddit on the keyless RSS
    channel so no third party sees the fetched URL.
    """
    return bool(state.settings.zyte_key) and state.settings.reddit_tier_policy == "robustness"


async def _fetch_via_zyte_oldreddit(url: str, *, state: AppState) -> TierResult | None:
    """Fetch a Reddit thread via Zyte raw mode on old.reddit; parse + assess.

    Returns:
      - a `Verdict.ok` TierResult with the scored/nested render + measured
        comment counts (+ a `comments_partial` info hint on shortfall) on success;
      - the Zyte `paid_auth_error` result (fail loud, no downgrade) on a bad key;
      - `None` on a transient Zyte failure, an unparseable page, or a zero-vs-
        positive-oracle miss — the caller then falls through to the RSS channel.
    """
    from ..tiers import Rendered, TierResult, ZyteTier

    _channel, old_url = rh.normalize(url)
    result = await ZyteTier().fetch(old_url, state=state, mode="httpResponseBody")

    if result.verdict is Verdict.paid_auth_error:
        return result  # authoritative hard-stop — surface the misconfiguration.
    if result.verdict is not Verdict.ok or not result.body:
        return None  # transient — let the keyless RSS channel try.

    thread = rh.parse_thread(result.body.decode("utf-8", errors="replace"))
    if thread is None:
        return None  # parse miss (old.reddit changed shape) → RSS fallback.

    loaded = len(thread.comments)
    total = thread.comment_total
    readiness = content_expectations.assess(loaded=loaded, total=total)
    if readiness == "fail":
        # Oracle says comments exist but none parsed — treat as a miss and let
        # RSS try (it may surface a sample) rather than return a comment-less
        # "success". If RSS also fails, its own never-silently-miss path fires.
        return None

    headings = [Heading(level=1, text=thread.title)] if thread.title else []
    byline = f"u/{thread.author}" if thread.author else None
    op_hint = comments_partial_hint(loaded=loaded, total=total) if readiness == "partial" and total is not None else None

    return TierResult(
        body=result.body,
        content_type="text/html",
        status_code=result.status_code,
        final_url=old_url,
        pre_rendered=Rendered(
            content_md=rh.render_markdown(thread),
            title=thread.title,
            byline=byline,
            headings=headings,
        ),
        operator_hint=op_hint,
        comments_loaded=loaded,
        comments_total=total,
        verdict=Verdict.ok,
    )


async def _resolve_short_url(url: str, *, state: AppState) -> str | None:
    """GET `redd.it/<id>` and return the resolved reddit URL, or None."""
    outcome = await fetch_bytes(
        url,
        headers={"User-Agent": state.settings.default_ua},
        timeout_s=_DEFAULT_TIMEOUT_S,
    )
    if outcome.verdict is not FetchVerdict.ok:
        return None
    final = outcome.final_url
    if not final or final == url:
        return None
    return final


async def _fetch_old_reddit_or_archive_signal(url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
    """Try old.reddit HTML; if that also produces nothing, signal archive."""
    result = await _fetch_old_reddit(url, state=state, cookies=cookies)
    if result.verdict == Verdict.ok and result.pre_rendered is not None:
        return result
    return _archive_escalation_signal(
        url,
        reason="reddit_deleted_try_archive",
        message="Reddit thread returned empty/404 on both RSS and old.reddit; try archive snapshot.",
    )


async def _fetch_old_reddit(url: str, *, state: AppState, cookies: dict[str, str] | None = None) -> TierResult:
    """Fallback: GET old.reddit.com<path> and extract HTML via trafilatura."""
    import trafilatura

    from ..tiers import Rendered, TierResult

    old_url = _to_old_reddit_url(url)
    outcome = await fetch_bytes(
        old_url,
        headers={"User-Agent": state.settings.default_ua},
        timeout_s=_DEFAULT_TIMEOUT_S,
        cookies=cookies,
    )
    if outcome.verdict is FetchVerdict.timeout:
        return empty_result(url, Verdict.timeout)
    if outcome.verdict is FetchVerdict.not_found:
        return empty_result(url, Verdict.not_found)
    if outcome.verdict is FetchVerdict.rate_limited:
        return empty_result(url, Verdict.rate_limited)
    if outcome.verdict is not FetchVerdict.ok:
        return empty_result(url, Verdict.connection_error)

    html = outcome.body.decode("utf-8", errors="replace")
    if not html:
        return empty_result(url, Verdict.length_floor)

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
        return empty_result(url, Verdict.length_floor)

    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata else None) or None
    author = (metadata.author if metadata else None) or None
    byline = author if author else None

    headings: list[Heading] = []
    if title:
        headings.append(Heading(level=1, text=title))

    return TierResult(
        body=outcome.body,
        content_type="text/html",
        status_code=outcome.status_code,
        final_url=old_url,
        headers=outcome.headers,
        pre_rendered=Rendered(
            content_md=markdown,
            title=title,
            byline=byline,
            headings=headings,
        ),
        verdict=Verdict.ok,
    )
