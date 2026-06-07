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
    if payload.source == "microdata":
        return _ld_json_to_markdown(_microdata_to_ld_shape(data))
    if payload.source == "opengraph":
        return _opengraph_to_markdown(data)
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
        if t == "Recipe":
            lines.append(_recipe_md(entry))
        elif t in ("Product", "Article", "NewsArticle"):
            lines.append(_single_entity_md(entry, kind=str(t)))
        elif t == "ItemList":
            items = entry.get("itemListElement") or []
            raw_rows = [item.get("item", item) if isinstance(item, dict) else None for item in items]
            rows = [_normalize_commerce_row(r) for r in raw_rows if isinstance(r, dict)]
            if rows:
                lines.append(_render_rows(rows, title="ItemList"))
        elif t == "BreadcrumbList":
            items = entry.get("itemListElement") or []
            names = [it.get("name") for it in items if isinstance(it, dict) and it.get("name")]
            if names:
                lines.append("**Breadcrumbs:** " + " > ".join(names))
    return "\n\n".join(s for s in lines if s)


def _framework_state_to_markdown(data: dict | list) -> str:
    rows = _find_product_or_item_list(data)
    if rows:
        rows = [_normalize_commerce_row(r) for r in rows]
        return _render_rows(rows, title="Listings")
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


# Known chrome dropped by the default-keep entity renderer — JSON-LD machinery
# is handled by the `@`-prefix check; these are media/self-reference keys whose
# values are never answer-bearing prose.
_ENTITY_NOISE_KEYS = frozenset({"image", "thumbnail", "thumbnailurl", "logo", "mainentityofpage"})
# Cap a single field's rendered value so a full `articleBody` (or similar) isn't
# dumped into a key-value line; the prose candidate already carries long text.
_ENTITY_VALUE_CAP = 500


def _scalar_kv(k: object, v: object) -> bool:
    """A renderable answer-bearing key/value: a non-`@` string key with a
    non-empty scalar value."""
    return isinstance(k, str) and not k.startswith("@") and isinstance(v, (str, int, float)) and str(v) != ""


def _recipe_md(entry: dict) -> str:
    """Render a JSON-LD `Recipe` — incl. its answer-bearing `NutritionInformation`.

    Content-agnostic: renders whichever nutrition fields are present (no
    number/unit special-casing). Defensive against shape variance — omits any
    field it cannot read, never raises.
    """
    name = entry.get("name") or "Recipe"
    lines = [f"## Recipe: {name}"]
    desc = entry.get("description")
    if isinstance(desc, str) and desc:
        lines.append(desc)
    for label, key in (("Yield", "recipeYield"), ("Prep", "prepTime"), ("Cook", "cookTime"), ("Total", "totalTime")):
        val = entry.get(key)
        if isinstance(val, (str, int, float)) and str(val):
            lines.append(f"- **{label}:** {val}")
    ingredients = entry.get("recipeIngredient")
    if isinstance(ingredients, list):
        items = [str(i) for i in ingredients if isinstance(i, (str, int, float)) and str(i)]
        if items:
            lines.append("- **Ingredients:** " + "; ".join(items))
    nutrition = entry.get("nutrition")
    if isinstance(nutrition, dict):
        parts = [f"{k} {v}" for k, v in nutrition.items() if _scalar_kv(k, v)]
        if parts:
            lines.append("- **Nutrition:** " + ", ".join(parts))
    return "\n".join(lines)


def _single_entity_md(entry: dict, *, kind: str) -> str:
    """Render a single JSON-LD entity by **default-keep** (ADR-0004): surface
    every answer-bearing scalar / shallow field in the entity's own order,
    dropping only JSON-LD machinery (`@`-keys), media/self-reference keys, and
    oversized values. No fixed `interesting_keys` allowlist — an unanticipated
    answer-bearing field (a `gtin`, a `material`) is no longer silently lost."""
    name = entry.get("name") or entry.get("headline") or "unnamed"
    lines = [f"## {kind}: {name}"]
    for key, val in entry.items():
        if not isinstance(key, str) or key.startswith("@") or key.lower() in _ENTITY_NOISE_KEYS:
            continue
        if isinstance(val, dict):
            inner = ", ".join(f"{k}={v}" for k, v in val.items() if _scalar_kv(k, v))
            if inner:
                lines.append(f"- **{key}:** {inner}")
        elif isinstance(val, list):
            scalars = [str(v) for v in val if isinstance(v, (str, int, float)) and str(v)]
            joined = ", ".join(scalars)
            if joined and len(joined) <= _ENTITY_VALUE_CAP:
                lines.append(f"- **{key}:** {joined}")
        elif isinstance(val, (str, int, float)):
            s = str(val)
            if s and len(s) <= _ENTITY_VALUE_CAP:
                lines.append(f"- **{key}:** {val}")
    return "\n".join(lines)


def _normalize_commerce_row(row: dict) -> dict:
    """Promote nested schema.org commerce fields to top-level scalars so the
    synth renderer can surface them: `offers.price` + `offers.priceCurrency`
    → a combined `price` token (e.g. `3690 TRY`), `offers.url` → `url`, and
    `aggregateRating.ratingValue` → `rating`. Flat-shaped rows (top-level
    scalar `price`/`url`) and non-commerce rows pass through unchanged."""
    if not isinstance(row, dict):
        return row
    out = dict(row)
    offers = row.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price")
        if price is not None and out.get("price") is None:
            currency = offers.get("priceCurrency")
            out["price"] = f"{price} {currency}" if currency else str(price)
        url = offers.get("url")
        if url and not out.get("url"):
            out["url"] = url
    rating = row.get("aggregateRating")
    if isinstance(rating, dict):
        rv = rating.get("ratingValue")
        if rv is not None and out.get("rating") is None:
            out["rating"] = rv
    return out


def _is_commerce_shaped(rows: list[dict]) -> bool:
    """A list is commerce-shaped when at least half its rows carry a (lifted)
    `price` or `url` — the gate that routes to linked-record rendering."""
    if not rows:
        return False
    hits = sum(1 for r in rows if isinstance(r, dict) and (r.get("price") is not None or r.get("url")))
    return hits * 2 >= len(rows)


def _render_rows(rows: list[dict], *, title: str) -> str:
    """Render row-shaped data: linked records for commerce-shaped lists
    (price/url preserved verbatim), the fixed-width table otherwise."""
    if _is_commerce_shaped(rows):
        return _rows_to_md_records(rows, title=title)
    return _rows_to_md_table(rows, title=title)


def _sanitize_link_text(text: str) -> str:
    """Make a string safe as markdown link text: drop `[`/`]` (which would
    terminate the link) and collapse any whitespace/newlines to single
    spaces."""
    return " ".join(str(text).replace("[", "").replace("]", "").split())


def _rows_to_md_records(rows: list[dict], *, title: str) -> str:
    """Render commerce rows as linked markdown records — one per item:
    `- [name](url) — 3690 TRY ⭐ 4.7`. The url is never length-capped (unlike
    the table's per-cell cap), so it stays verbatim for try_url drilldowns.
    Absent fields are omitted; `image` is intentionally not rendered."""
    lines: list[str] = []
    for row in rows[:50]:  # cap synthetic output, matching _find_product_or_item_list
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("headline") or row.get("title")
        url = row.get("url")
        if not name and not url:
            continue
        if url and name:
            head = f"[{_sanitize_link_text(name)}]({url})"
        elif name:
            head = _sanitize_link_text(name)
        else:
            head = str(url)
        extras: list[str] = []
        price = row.get("price")
        if price is not None and str(price) != "":
            extras.append(str(price))
        rating = row.get("rating")
        if rating is not None and str(rating) != "":
            extras.append(f"⭐ {rating}")
        line = f"- {head}"
        if extras:
            line += " — " + " ".join(extras)
        lines.append(line)
    if not lines:
        return ""
    return f"### {title}\n\n" + "\n".join(lines)


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


# --------------------------------------------------------------------- #
# extruct adapters (v0.18)
# --------------------------------------------------------------------- #


def _microdata_to_ld_shape(data: dict | list) -> list[dict]:
    """Flatten extruct's microdata output into LD-JSON shape so the existing
    LD walker can consume it.

    Extruct emits `{"type": ["https://schema.org/Product"], "properties":
    {"name": "...", "offers": {...}, ...}}`. We map `type` → `@type` (last
    URL segment, e.g. `Product`), promote `properties` to direct keys.
    """
    items: list[dict] = []
    if isinstance(data, list):
        items = [it for it in data if isinstance(it, dict)]
    elif isinstance(data, dict):
        items = [data]
    out: list[dict] = []
    for it in items:
        raw_types = it.get("type") or it.get("@type")
        type_value: str | list[str] | None = None
        if isinstance(raw_types, str):
            type_value = raw_types.rsplit("/", 1)[-1]
        elif isinstance(raw_types, list):
            type_value = [t.rsplit("/", 1)[-1] for t in raw_types if isinstance(t, str)]
        raw_props = it.get("properties")
        props: dict = raw_props if isinstance(raw_props, dict) else {}
        entry: dict[str, Any] = {"@type": type_value} if type_value is not None else {}
        for k, v in props.items():
            entry[k] = v
        out.append(entry)
    return out


def _opengraph_to_markdown(data: dict | list) -> str:
    """Render the OpenGraph dict as a two-column markdown table. Cap at 50 rows.

    The extractor emits a flat `{property: content}` dict for OG; this adapter
    treats list input defensively in case a future producer chooses that shape.
    """
    flat: dict[str, str] = {}
    if isinstance(data, dict):
        flat = {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                for k, v in entry.items():
                    if isinstance(v, (str, int, float)):
                        flat[str(k)] = str(v)
    if not flat:
        return ""
    rows = list(flat.items())[:50]
    lines = ["### OpenGraph", "", "| property | value |", "| --- | --- |"]
    lines.extend(f"| {k} | {v.replace('|', '/')[:200]} |" for k, v in rows)
    return "\n".join(lines)
