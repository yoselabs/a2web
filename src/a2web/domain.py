"""a2web domain-coupled glue.

Functions that read `AppSettings` or domain models but are too small to deserve
their own module. Lives at the top level of the package because the previous
seam directories (`cache/`, `gate/`, `extract/`, `log/`, `proxy/`) have been
deleted — there's no natural per-domain home for these.

**This description became true on 2026-08-01.** It previously sat above 551
lines of which 381 (69%) were a structured-data → markdown renderer that read
neither settings nor models and had zero a2web imports. That renderer now lives
at `packages/structured_render.py`; what remains is URL policy plus the twelve
settings-coupled lines the docstring was always describing.

**`is_search_shaped` cannot follow it.** It gates one clause of
`actions.empty.is_confirmed_empty` — the ADR-level empty→ok conjunction — so it
is domain policy wearing a URL predicate's clothes, and it stays here.

Pure functions only. No I/O. No class state.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, quote, urlparse

if TYPE_CHECKING:
    from .settings import AppSettings

__all__ = (
    "compute_profile_hash",
    "is_live_only",
    "is_search_shaped",
    "rewrite_captcha_host",
    "strip_reader_prefix",
)

# Path segments that mark a search / listing surface — where an "empty result"
# reading is credible. An empty reading of a NON-search route (an article, a
# product page) is itself suspicious, so the empty-confirmation conjunction
# (`actions.empty.is_confirmed_empty`) requires one of these OR a query string.
_SEARCH_PATH_SEGMENTS = frozenset({"search", "arama", "ara", "results", "sr", "find", "query"})


def is_search_shaped(url: str) -> bool:
    """True when a URL looks like a search/listing query — it carries a `?…`
    query string OR a search-shaped path segment. Pure and total: a malformed URL
    yields False, never raises. Used to gate the empty→ok promotion (an empty
    reading is only credible on a query surface)."""
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    if parsed.query:
        return True
    segments = (parsed.path or "").lower().split("/")
    return any(seg in _SEARCH_PATH_SEGMENTS for seg in segments)


# Cap the never-lose JSON text fallback so an unbounded API dump can't blow the
# response envelope (mirrors the synthetic-output caps elsewhere in this module).
# Hosts that emit captcha pages on `/search` for unauth scrapers.
# Pre-routed to DuckDuckGo's HTML endpoint before tier dispatch.
_CAPTCHA_SEARCH_HOSTS = frozenset(
    {
        "google.com",
        "www.google.com",
        "bing.com",
        "www.bing.com",
    }
)


def compute_profile_hash(settings: AppSettings) -> str:
    """Hash settings fields that affect upstream request shape.

    Fed into `(url, profile_hash)` cache keys so a UA change or stealth
    toggle invalidates cached entries without manual eviction.
    """
    payload = f"{settings.default_ua}|{settings.stealth}".encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def is_live_only(url: str, settings: AppSettings) -> bool:
    """Return True if `url`'s host should bypass the cache entirely."""
    host = urlparse(url).hostname or ""
    return any(host == h or host.endswith(f".{h}") for h in settings.live_only_hosts)


def rewrite_captcha_host(url: str) -> str | None:
    """Rewrite known-captcha search endpoints to DuckDuckGo HTML.

    Google and Bing serve captcha pages on `/search` for unauth scrapers.
    The captcha pages pass our length floor and look like "raw ok" content —
    a silent failure for callers that just want search results.

    Returns:
        A `https://duckduckgo.com/html/?q=<urlencoded-q>` URL when `url`
        matches a known captcha host AND has a `?q=` parameter; None
        otherwise. Non-search paths on captcha hosts (Maps, Drive, Images,
        etc.) pass through unchanged (caller sees `None` and proceeds).

    Pure function — no I/O.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _CAPTCHA_SEARCH_HOSTS:
        return None
    path = parsed.path or ""
    # Only rewrite the search endpoint. Other Google/Bing subpaths (Maps,
    # Drive, Images) are passed through unchanged — handler / raw will
    # do whatever's right for those.
    if path not in ("/search", "/search/"):
        return None
    q_list = parse_qs(parsed.query).get("q") or []
    q = q_list[0] if q_list else ""
    if not q:
        return None
    return f"https://duckduckgo.com/html/?q={quote(q)}"


# Reader-service prefixes an agent may have wrapped a URL in, unaware that
# a2web runs the reader itself as an internal fallback tier. Left in place, the
# prefix pins a2web to that single tier (it treats the reader host as the origin)
# with no raw/browser/paid fallback — the opposite of resilience.
_READER_PREFIXES: tuple[str, ...] = (
    "https://r.jina.ai/",
    "http://r.jina.ai/",
    "r.jina.ai/",
)


def strip_reader_prefix(url: str) -> str | None:
    """Unwrap an incoming reader-wrapped URL to its real target.

    When a caller passes `https://r.jina.ai/<real-url>`, return `<real-url>` so
    a2web fetches the true target with its full tier ladder and owns its own
    reader fallback. Returns None when `url` carries no reader prefix, or when the
    prefix has no inner URL (a bare `r.jina.ai/` is left untouched). Pure — no I/O.
    """
    for prefix in _READER_PREFIXES:
        if url.startswith(prefix):
            inner = url[len(prefix) :]
            # Only unwrap when the remainder is itself an http(s) URL — a bare
            # reader host, or a reader path that is not a wrapped URL, is left alone.
            if inner.startswith(("http://", "https://")):
                return inner
            return None
    return None
