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
from dataclasses import dataclass
from typing import Literal

from selectolax.parser import HTMLParser

JsonSource = Literal["next_data", "nuxt_data", "ld_json", "generic"]


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
    for node in tree.css('script#__NEXT_DATA__'):
        body = node.text(strip=False) or ""
        payload = _try_parse(body)
        if payload is not None:
            out.append(JsonPayload(source="next_data", data=payload, script_id="__NEXT_DATA__", byte_size=len(body)))

    # 2. __NUXT_DATA__
    for node in tree.css('script#__NUXT_DATA__'):
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

    return out


def rank_payloads(payloads: list[JsonPayload]) -> list[JsonPayload]:
    """Order payloads by descending downstream value.

    Priority rules:
    - LD-JSON carrying a recognized schema (`Product`, `Article`, `ItemList`,
      `BreadcrumbList`, `NewsArticle`) with ≥3 populated fields ranks first.
    - Then `next_data` / `nuxt_data` (framework app state — usually richest).
    - Then weak LD-JSON (below the field threshold).
    - Then `generic` app-state.

    Within each bucket, larger payloads rank first (more data to synthesize).
    """

    def bucket(p: JsonPayload) -> int:
        if p.source == "ld_json" and _ld_json_strong(p.data):
            return 0
        if p.source in ("next_data", "nuxt_data"):
            return 1
        if p.source == "ld_json":
            return 2
        return 3  # generic

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


__all__ = ["JsonPayload", "JsonSource", "extract_json_payloads", "rank_payloads"]
