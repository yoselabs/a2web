"""OpenGraph + Twitter + JSON-LD metadata parser. Sync, pure."""

from __future__ import annotations

import json
from typing import Any

from selectolax.parser import HTMLParser


def _flatten_jsonld(obj: Any, prefix: str, out: dict[str, str]) -> None:
    """Best-effort flatten of one JSON-LD object into dot-keyed strings.

    Only top-level scalar fields end up in `out`. Nested objects/arrays are
    skipped — agents and the renderer rarely need deep traversal, and the
    envelope stays compact.
    """
    if not isinstance(obj, dict):
        return
    for key, value in obj.items():
        if isinstance(value, str | int | float | bool):
            out[f"{prefix}.{key}"] = str(value)


def parse_metadata(html: str) -> dict[str, str]:
    """Return a flat dot-keyed dict of OG, Twitter, and JSON-LD metadata.

    Missing fields are simply omitted from the dict (no `None` values).
    Only the first JSON-LD block is parsed (`jsonld[0].*`). Pure function.
    """
    out: dict[str, str] = {}
    tree = HTMLParser(html)

    for meta in tree.css("meta[property^='og:']"):
        prop = meta.attributes.get("property") or ""
        content = meta.attributes.get("content") or ""
        if prop and content:
            key = prop.replace(":", ".", 1)
            out[key] = content

    for meta in tree.css("meta[name^='twitter:']"):
        name = meta.attributes.get("name") or ""
        content = meta.attributes.get("content") or ""
        if name and content:
            key = name.replace(":", ".", 1)
            out[key] = content

    jsonld_nodes = tree.css("script[type='application/ld+json']")
    if jsonld_nodes:
        raw = (jsonld_nodes[0].text() or "").strip()
        if raw:
            try:
                obj = json.loads(raw)
                first = obj[0] if isinstance(obj, list) and obj else obj
                _flatten_jsonld(first, "jsonld[0]", out)
            except (ValueError, IndexError):
                pass

    return out
