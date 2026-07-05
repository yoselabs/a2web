"""JSON-in-script payload extractor — in-tree microsoftware.

Modern SPAs (Next.js, Nuxt) and most product/article pages embed structured
data as a `<script type="application/json">` blob. Trafilatura strips these,
leaving only the navigation chrome. This extractor pulls them back out so
the a2web seam can synthesize a markdown table the LLM prompt understands.

Zero a2web-domain imports. Boundary type `JsonPayload` is package-owned;
the domain converts to a synthetic markdown surface via `domain.py`.

Gherkin (mirrors spec at openspec/changes/harsh-test-session-fixes/specs/json-extract/spec.md):

    Scenario: Next.js page yields __NEXT_DATA__ payload
      When the extractor scans HTML containing a `<script id="__NEXT_DATA__">`
        with a parseable JSON body
      Then a JsonPayload with source="next_data" is returned

    Scenario: JSON-LD Product schema is detected
      When the extractor scans HTML with `<script type="application/ld+json">`
        carrying a Product with offers and aggregateRating
      Then a JsonPayload with source="ld_json" is returned

    Scenario: Malformed JSON does not raise
      When the extractor encounters a matching script tag with a body that
        fails to parse as JSON
      Then that tag is silently skipped; other tags on the page still emit

    Scenario: Product LD-JSON wins over Next.js pageProps
      When a page has both __NEXT_DATA__ and JSON-LD Product (≥3 populated fields)
      Then rank_payloads returns the LD-JSON payload first

    Scenario: Empty LD-JSON loses to populated Next.js payload
      When a page has both, but the LD-JSON has <3 populated schema fields
      Then rank_payloads returns the next_data payload first
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from selectolax.parser import HTMLParser

JsonSource = Literal[
    "next_data",
    "nuxt_data",
    "ld_json",
    "generic",
    "window_var",
    "microdata",
    "opengraph",
]


@dataclass(slots=True, frozen=True)
class JsonPayload:
    """A parsed JSON-in-script payload extracted from HTML.

    `source` identifies the detector that matched (stable contract for
    downstream prioritization). `data` is the parsed JSON (dict or list —
    LD-JSON `@graph` can be a list at the root). `script_id` is the
    matched tag's `id` attribute when present (None for `application/json`
    tags without ids). `byte_size` is the length of the source JSON text.
    """

    source: JsonSource
    data: dict | list
    script_id: str | None
    byte_size: int


# --------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------- #


_PREFERRED_LD_TYPES: frozenset[str] = frozenset({"Product", "Article", "NewsArticle", "ItemList", "BreadcrumbList"})
_MIN_LD_FIELDS: int = 3


def extract_json_payloads(html: str) -> list[JsonPayload]:
    """Scan `html` for known JSON-in-script shapes and return parsed payloads.

    Order of detection (not priority — that's `rank_payloads`'s job):
    1. `<script id="__NEXT_DATA__" type="application/json">`
    2. `<script id="__NUXT_DATA__">`
    3. `<script type="application/ld+json">` (may appear multiple times)
    4. `<script type="application/json"[data-*]>` — generic app-state

    Malformed JSON is silently skipped per the spec.
    """
    if not html:
        return []
    try:
        tree = HTMLParser(html)
    except Exception:
        return []

    out: list[JsonPayload] = []

    # 1. __NEXT_DATA__
    for node in tree.css("script#__NEXT_DATA__"):
        body = node.text(strip=False) or ""
        payload = _try_parse(body)
        if payload is not None:
            out.append(JsonPayload(source="next_data", data=payload, script_id="__NEXT_DATA__", byte_size=len(body)))

    # 2. __NUXT_DATA__
    for node in tree.css("script#__NUXT_DATA__"):
        body = node.text(strip=False) or ""
        payload = _try_parse(body)
        if payload is not None:
            out.append(JsonPayload(source="nuxt_data", data=payload, script_id="__NUXT_DATA__", byte_size=len(body)))

    # 3. application/ld+json (often multiple per page)
    for node in tree.css('script[type="application/ld+json"]'):
        body = node.text(strip=False) or ""
        payload = _try_parse(body)
        if payload is not None:
            out.append(JsonPayload(source="ld_json", data=payload, script_id=node.attributes.get("id"), byte_size=len(body)))

    # 4. generic application/json with a data-* attribute (Yandex-style app-state)
    for node in tree.css('script[type="application/json"]'):
        # Skip ones already captured by id selectors above.
        if node.attributes.get("id") in ("__NEXT_DATA__", "__NUXT_DATA__"):
            continue
        body = node.text(strip=False) or ""
        payload = _try_parse(body)
        if payload is not None:
            out.append(JsonPayload(source="generic", data=payload, script_id=node.attributes.get("id"), byte_size=len(body)))

    # 5. Microdata + OpenGraph — selectolax-native attribute walk.
    out.extend(_extract_microdata_and_og(tree))

    # 6. window.<name> = {...} JS-variable assignments inside text/javascript
    # scripts. Targets initial-state patterns common to older / custom SPAs
    # (Yandex's `window.state`, classic Redux `window.__INITIAL_STATE__`,
    # generic `window.__PRELOADED_STATE__` / `window.__APP_DATA__`).
    for node in tree.css("script"):
        script_type = (node.attributes.get("type") or "").lower()
        # Skip the application/json paths handled above and external scripts.
        if script_type and script_type not in ("text/javascript", "application/javascript", "module"):
            continue
        body = node.text(strip=False) or ""
        if not body or len(body) < 32:
            continue
        for var_name, expr in _scan_window_var_assignments(body):
            parsed = _try_parse(expr)
            if parsed is not None:
                out.append(
                    JsonPayload(
                        source="window_var",
                        data=parsed,
                        script_id=var_name,  # repurpose: carries the window.<name>
                        byte_size=len(expr),
                    )
                )

    return out


def rank_payloads(payloads: list[JsonPayload]) -> list[JsonPayload]:
    """Order payloads by descending downstream value.

    Bucket order (v0.18 — adds microdata + opengraph):
      0. ld_json strong (Product/Article/ItemList/BreadcrumbList/NewsArticle ≥3 fields)
      1. microdata strong (same @type set, ≥3 fields)
      2. next_data, nuxt_data (framework app state)
      3. opengraph (metadata, not body — always after framework state)
      4. ld_json weak, microdata weak
      5. window_var
      6. generic

    Within each bucket, larger payloads rank first (more data to synthesize).
    """

    def bucket(p: JsonPayload) -> int:
        if p.source == "ld_json" and _ld_json_strong(p.data):
            return 0
        if p.source == "microdata" and _microdata_strong(p.data):
            return 1
        if p.source in ("next_data", "nuxt_data"):
            return 2
        if p.source == "opengraph":
            return 3
        if p.source in ("ld_json", "microdata"):
            return 4
        if p.source == "window_var":
            return 5
        return 6  # generic

    return sorted(payloads, key=lambda p: (bucket(p), -p.byte_size))


def _ld_json_strong(data: dict | list) -> bool:
    """A LD-JSON payload is 'strong' if it (or a top-level @graph entry) is
    one of the preferred types AND has ≥3 populated fields beyond `@type` /
    `@context`.

    Real-world LD-JSON often nests inside `@graph`; we walk one level down.
    """
    candidates: list[dict] = []
    if isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            candidates.extend(item for item in data["@graph"] if isinstance(item, dict))
        candidates.append(data)
    elif isinstance(data, list):
        candidates.extend(item for item in data if isinstance(item, dict))

    for entry in candidates:
        entry_type = entry.get("@type")
        # @type can be a string or a list of strings.
        types: set[str] = set()
        if isinstance(entry_type, str):
            types.add(entry_type)
        elif isinstance(entry_type, list):
            types.update(t for t in entry_type if isinstance(t, str))
        if not types & _PREFERRED_LD_TYPES:
            continue
        populated = sum(1 for k, v in entry.items() if not k.startswith("@") and v not in (None, "", [], {}))
        if populated >= _MIN_LD_FIELDS:
            return True
    return False


# Names worth scanning. Conservative list — only patterns that, when present,
# carry initial app/page state. NOT generic `window.foo` (would over-match).
_WINDOW_VAR_NAMES: tuple[str, ...] = (
    "state",
    "__INITIAL_STATE__",
    "__PRELOADED_STATE__",
    "__APP_DATA__",
    "__APP_STATE__",
    "__DATA__",
    "__REDUX_STATE__",
    "__SSR__",
    "__APOLLO_STATE__",
    "__NUXT__",
)
_WINDOW_VAR_PREFIXES: tuple[re.Pattern[str], ...] = tuple(re.compile(rf"\bwindow\.{re.escape(name)}\s*=\s*") for name in _WINDOW_VAR_NAMES)


def _scan_window_var_assignments(js: str) -> list[tuple[str, str]]:
    """Find `window.<NAME> = {...}` assignments in a JS body.

    Returns a list of `(var_name, json_expression_text)` tuples. The
    expression text is the substring from the first `{` (or `[`) after the
    `=` up through the matching balanced closer, scanned with string-aware
    bracket counting. Only NAMEs in `_WINDOW_VAR_NAMES` are scanned.

    No JS evaluation — only patterns where the right-hand side parses as
    JSON survive `_try_parse` downstream.
    """
    out: list[tuple[str, str]] = []
    for name, prefix_re in zip(_WINDOW_VAR_NAMES, _WINDOW_VAR_PREFIXES, strict=True):
        for m in prefix_re.finditer(js):
            start = m.end()
            if start >= len(js):
                continue
            opener = js[start]
            if opener not in "{[":
                continue
            closer = "}" if opener == "{" else "]"
            depth = 0
            in_string: str | None = None  # quote char when inside a string
            i = start
            n = len(js)
            while i < n:
                ch = js[i]
                if in_string is not None:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == in_string:
                        in_string = None
                elif ch in ('"', "'"):
                    in_string = ch
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        out.append((name, js[start : i + 1]))
                        break
                i += 1
    return out


def _try_parse(body: str) -> dict | list | None:
    """Parse `body` as JSON; return the parsed value (dict or list) on success,
    None on failure (malformed JSON, or root is a non-container scalar).
    """
    if not body or not body.strip():
        return None
    try:
        parsed = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


# --------------------------------------------------------------------- #
# extruct integration — microdata, RDFa, OpenGraph
# --------------------------------------------------------------------- #


def _extract_microdata_and_og(tree: HTMLParser) -> list[JsonPayload]:
    """Pull HTML5 microdata + OpenGraph meta tags directly off the selectolax
    tree. No extruct / rdflib dependency — the spec for both is a tractable
    attribute walk.

    RDFa is intentionally not covered: open-web hit rate is academic-only and
    the rdflib-shaped cost (transitive ~MB) isn't justified by the eval
    corpus today. Add a dedicated path if a real RDFa-shaped failure surfaces.
    """
    out: list[JsonPayload] = []

    items = _walk_microdata(tree)
    if items:
        try:
            byte_size = len(json.dumps(items))
        except (TypeError, ValueError):
            byte_size = 0
        out.append(JsonPayload(source="microdata", data=items, script_id=None, byte_size=byte_size))

    og = _collect_opengraph(tree)
    if og:
        try:
            byte_size = len(json.dumps(og))
        except (TypeError, ValueError):
            byte_size = 0
        out.append(JsonPayload(source="opengraph", data=og, script_id=None, byte_size=byte_size))

    return out


# Microdata HTML5 value-extraction table (per WHATWG spec §5.2.6 "Values"):
# the source attribute varies by tag.
_MICRODATA_VALUE_ATTR: dict[str, str] = {
    "meta": "content",
    "audio": "src",
    "embed": "src",
    "iframe": "src",
    "img": "src",
    "source": "src",
    "track": "src",
    "video": "src",
    "a": "href",
    "area": "href",
    "link": "href",
    "object": "data",
    "data": "value",
    "meter": "value",
    "time": "datetime",
}


def _walk_microdata(tree: HTMLParser) -> list[dict]:
    """Walk every top-level [itemscope] node and collect its properties.

    Returns a list of `{"type": [<itemtype>, ...], "properties": {<itemprop>:
    <value or nested item>}}` records. Nested itemscope items recurse as
    dicts under the parent's properties.

    Top-level = scope nodes whose nearest [itemscope] ancestor is themselves.
    """
    scopes = tree.css("[itemscope]")
    if not scopes:
        return []
    out: list[dict] = []
    for node in scopes:
        # Skip if a parent is also itemscope (we only want top-level entries).
        parent = node.parent
        nested = False
        while parent is not None:
            attrs = parent.attributes
            if attrs is not None and "itemscope" in attrs:
                nested = True
                break
            parent = parent.parent
        if nested:
            continue
        out.append(_extract_microdata_item(node))
    return out


def _extract_microdata_item(scope_node: Any) -> dict:
    itemtype = (scope_node.attributes.get("itemtype") or "").strip()
    types = [t for t in itemtype.split() if t]
    properties: dict[str, Any] = {}

    # Collect [itemprop] descendants that do not belong to a deeper itemscope.
    for prop in scope_node.css("[itemprop]"):
        if prop == scope_node:
            continue
        # Walk up to confirm `prop` is owned by `scope_node` (not a nested scope).
        parent = prop.parent
        owner: Any = None
        while parent is not None:
            attrs = parent.attributes
            if attrs is not None and "itemscope" in attrs:
                owner = parent
                break
            parent = parent.parent
        if owner != scope_node:
            continue

        names = (prop.attributes.get("itemprop") or "").split()
        if not names:
            continue

        prop_attrs = prop.attributes
        if prop_attrs is not None and "itemscope" in prop_attrs:
            value: Any = _extract_microdata_item(prop)
        else:
            value = _microdata_value_of(prop)

        for name in names:
            existing = properties.get(name)
            if existing is None:
                properties[name] = value
            elif isinstance(existing, list):
                existing.append(value)
            else:
                properties[name] = [existing, value]

    return {"type": types, "properties": properties}


def _microdata_value_of(node: Any) -> str:
    tag = (node.tag or "").lower()
    attr = _MICRODATA_VALUE_ATTR.get(tag)
    if attr:
        value = node.attributes.get(attr)
        if value is not None:
            return value
    return (node.text(strip=True) or "").strip()


_OG_PROPERTY_PREFIXES: tuple[str, ...] = ("og:", "article:", "product:", "book:", "profile:")


def _collect_opengraph(tree: HTMLParser) -> dict[str, str]:
    """Collect every <meta property="<og|article|product|book|profile>:*">.

    Returns a flat `{property: content}` dict (last-write-wins for duplicates).
    Empty dict when nothing matches.
    """
    out: dict[str, str] = {}
    for node in tree.css("meta[property]"):
        prop = (node.attributes.get("property") or "").strip()
        if not prop.startswith(_OG_PROPERTY_PREFIXES):
            continue
        content = (node.attributes.get("content") or "").strip()
        if not content:
            continue
        out[prop] = content
    return out


def _microdata_strong(data: dict | list) -> bool:
    """Mirror of `_ld_json_strong` for extruct's microdata output.

    Microdata items come through as `{"type": ["https://schema.org/Product"],
    "properties": {...}}`. Strong = recognized @type set + ≥3 populated
    non-`@`-prefixed properties.
    """
    items: list[dict] = []
    if isinstance(data, list):
        items = [it for it in data if isinstance(it, dict)]
    elif isinstance(data, dict):
        items = [data]

    for entry in items:
        raw_types = entry.get("type") or entry.get("@type")
        types: set[str] = set()
        if isinstance(raw_types, str):
            types.add(raw_types.rsplit("/", 1)[-1])
        elif isinstance(raw_types, list):
            for t in raw_types:
                if isinstance(t, str):
                    types.add(t.rsplit("/", 1)[-1])
        if not types & _PREFERRED_LD_TYPES:
            continue
        raw_props = entry.get("properties")
        props: dict = raw_props if isinstance(raw_props, dict) else entry
        populated = sum(1 for k, v in props.items() if not k.startswith("@") and v not in (None, "", [], {}))
        if populated >= _MIN_LD_FIELDS:
            return True
    return False


# --------------------------------------------------------------------- #
# Whole-response JSON (not JSON-in-script) — json-endpoint-direct-routing
# --------------------------------------------------------------------- #


def is_json_content_type(content_type: str | None) -> bool:
    """Return True for a JSON-family content-type.

    Matches `application/json`, `text/json`, and any `application/<x>+json`
    suffix type (e.g. `application/vnd.api+json`, `application/ld+json`).
    Case-insensitive; tolerant of a trailing `; charset=` parameter. This is
    the single source of truth both the raw tier and the orchestrator consult,
    so they agree on what counts as a JSON response.
    """
    if not content_type:
        return False
    ct = content_type.split(";", 1)[0].strip().lower()
    if ct in ("application/json", "text/json"):
        return True
    return ct.startswith("application/") and ct.endswith("+json")


def parse_json_response(text: str) -> JsonPayload | None:
    """Parse a whole response body as a single top-level JSON document.

    Returns a `JsonPayload(source="generic")` on success, or `None` on any
    parse failure or a non-object/array root (the caller falls back to normal
    handling — never raises). Owns `json.loads` for the response-body path, so
    the json-loads funnel invariant stays intact (no `json.loads` is added
    outside this package).
    """
    stripped = text.strip()
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, (dict, list)):
        return None
    return JsonPayload(source="generic", data=data, script_id=None, byte_size=len(text))


__all__ = [
    "JsonPayload",
    "JsonSource",
    "extract_json_payloads",
    "is_json_content_type",
    "parse_json_response",
    "rank_payloads",
]
