"""a2web domain-coupled glue.

Functions that read `AppSettings` or domain models but are too small
to deserve their own module. Lives at the top level of the package
because the previous seam directories (`cache/`, `gate/`, `extract/`,
`log/`, `proxy/`) have been deleted — there's no natural per-domain
home for these.

Pure functions only. No I/O. No class state.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote, urlparse

if TYPE_CHECKING:
    from .packages.json_in_script import JsonPayload
    from .settings import AppSettings

__all__ = (
    "compute_profile_hash",
    "is_live_only",
    "json_to_markdown_rows",
    "rewrite_captcha_host",
)


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


# --------------------------------------------------------------------- #
# JSON synthesis (v0.10 — harsh-test-session-fixes)
# --------------------------------------------------------------------- #


def json_to_markdown_rows(payload: JsonPayload) -> str:
    """Convert a `JsonPayload` to a synthetic markdown surface for the
    extractor LLM.

    Only known shapes are converted; unknown shapes return an empty string
    (the caller will then fall back to the original trafilatura output).
    Recognized shapes:

    * LD-JSON `Product` / `NewsArticle` / `Article` (single or `@graph`)
    * LD-JSON `ItemList` (`itemListElement`)
    * Next.js `props.pageProps.products` / `props.pageProps.items`
    * Generic `products` / `items` array at the root

    The output is a markdown table when the data is row-shaped, or a
    `**key:** value` list when it's a single entity. Empty input → empty
    output (do-no-harm contract).
    """
    if payload is None:
        return ""
    data = payload.data
    if payload.source == "ld_json":
        return _ld_json_to_markdown(data)
    if payload.source in ("next_data", "nuxt_data", "window_var", "generic"):
        return _framework_state_to_markdown(data)
    return ""


def _ld_json_to_markdown(data: dict | list) -> str:
    entries = _collect_ld_entries(data)
    if not entries:
        return ""
    lines: list[str] = []
    for entry in entries:
        t = entry.get("@type")
        if isinstance(t, list):
            t = t[0] if t else None
        if t in ("Product", "Article", "NewsArticle"):
            lines.append(_single_entity_md(entry, kind=str(t)))
        elif t == "ItemList":
            items = entry.get("itemListElement") or []
            rows = [item.get("item", item) if isinstance(item, dict) else None for item in items]
            rows = [r for r in rows if isinstance(r, dict)]
            if rows:
                lines.append(_rows_to_md_table(rows, title="ItemList"))
        elif t == "BreadcrumbList":
            items = entry.get("itemListElement") or []
            names = [it.get("name") for it in items if isinstance(it, dict) and it.get("name")]
            if names:
                lines.append("**Breadcrumbs:** " + " > ".join(names))
    return "\n\n".join(s for s in lines if s)


def _framework_state_to_markdown(data: dict | list) -> str:
    rows = _find_product_or_item_list(data)
    if rows:
        return _rows_to_md_table(rows, title="Listings")
    return ""


def _collect_ld_entries(data: dict | list) -> list[dict]:
    out: list[dict] = []
    if isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            out.extend(item for item in graph if isinstance(item, dict))
        else:
            out.append(data)
    elif isinstance(data, list):
        out.extend(item for item in data if isinstance(item, dict))
    return out


def _find_product_or_item_list(data: Any, depth: int = 0) -> list[dict]:
    """Walk the JSON looking for a list of objects under a key like
    `products`, `items`, `results`, `entities`. Capped at depth 6 so we
    don't explore the entire app state."""
    if depth > 6:
        return []
    if isinstance(data, dict):
        for key in ("products", "items", "results", "entities", "list"):
            v = data.get(key)
            if isinstance(v, list) and v and all(isinstance(item, dict) for item in v):
                return v[:50]  # cap synthetic output
        for v in data.values():
            found = _find_product_or_item_list(v, depth + 1)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_product_or_item_list(item, depth + 1)
            if found:
                return found
    return []


def _single_entity_md(entry: dict, *, kind: str) -> str:
    name = entry.get("name") or entry.get("headline") or "unnamed"
    lines = [f"## {kind}: {name}"]
    interesting_keys = (
        "name", "headline", "brand", "description", "datePublished", "author",
        "offers", "aggregateRating", "sku", "price", "priceCurrency", "availability",
    )
    for key in interesting_keys:
        if key not in entry:
            continue
        val = entry[key]
        if isinstance(val, dict):
            inner = ", ".join(f"{k}={v}" for k, v in val.items() if not k.startswith("@") and v)
            if inner:
                lines.append(f"- **{key}:** {inner}")
        elif isinstance(val, (str, int, float)):
            lines.append(f"- **{key}:** {val}")
    return "\n".join(lines)


def _rows_to_md_table(rows: list[dict], *, title: str) -> str:
    # Choose columns from the first row's keys (capped to keep tables readable).
    columns: list[str] = []
    for row in rows[:5]:  # sample first 5 rows for column inference
        for k, v in row.items():
            if k.startswith("@") or isinstance(v, (dict, list)):
                continue
            if k not in columns:
                columns.append(k)
        if len(columns) >= 8:
            break
    columns = columns[:8]
    if not columns:
        return ""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body_lines = []
    for row in rows:
        cells = []
        for k in columns:
            v = row.get(k, "")
            if isinstance(v, (dict, list)):
                v = ""
            cells.append(str(v).replace("|", "/")[:80])
        body_lines.append("| " + " | ".join(cells) + " |")
    return f"### {title}\n\n" + "\n".join([header, sep, *body_lines])

