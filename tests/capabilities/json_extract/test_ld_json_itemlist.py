"""JSON-LD `ItemList` synthesis — `json_to_markdown_rows`.

`json_in_script` already detects `ld_json` payloads and `rank_payloads`
already prefers `ItemList`; this covers the synthesis adapter rendering an
`ItemList` into record rows.
"""

from __future__ import annotations

from a2web.domain import json_to_markdown_rows
from a2web.packages.json_in_script import JsonPayload


def _ld_payload(data: dict) -> JsonPayload:
    return JsonPayload(source="ld_json", data=data, script_id=None, byte_size=len(str(data)))


def test_itemlist_renders_record_rows() -> None:
    data = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {"name": "First item", "url": "https://example.com/1"}},
            {"@type": "ListItem", "position": 2, "item": {"name": "Second item", "url": "https://example.com/2"}},
            {"@type": "ListItem", "position": 3, "item": {"name": "Third item", "url": "https://example.com/3"}},
        ],
    }
    md = json_to_markdown_rows(_ld_payload(data))
    assert "First item" in md
    assert "Third item" in md
    assert "https://example.com/1" in md


def test_empty_itemlist_yields_no_rows() -> None:
    md = json_to_markdown_rows(_ld_payload({"@type": "ItemList", "itemListElement": []}))
    assert md == ""


def test_malformed_itemlist_yields_no_rows() -> None:
    md = json_to_markdown_rows(_ld_payload({"@type": "ItemList", "itemListElement": "not-a-list"}))
    assert md == ""
