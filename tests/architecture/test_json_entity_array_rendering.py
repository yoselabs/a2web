"""`structured-entity-array-rendering`: a list-of-dicts entity field (e.g.
`Organization.contactPoint` holding multiple `ContactPoint` entries) must
render each entry distinctly, not silently vanish.

Before this change, `_single_entity_md`'s list-value branch only kept bare
scalars; a list of dicts produced an empty joined string and the whole field
was dropped with no signal that anything was lost — despite `_single_entity_md`
claiming a "default-keep" (ADR-0004) philosophy for exactly this kind of
unanticipated-but-answer-bearing field.
"""

from __future__ import annotations

from json_in_html import JsonPayload

from a2web.domain import json_to_markdown_rows


def _payload(data: dict) -> JsonPayload:
    return JsonPayload(source="ld_json", data=data, script_id=None, byte_size=64)


def test_array_of_contact_points_renders_each_entry_distinctly() -> None:
    payload = _payload(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": "Acme Corp",
            "contactPoint": [
                {"@type": "ContactPoint", "telephone": "+1-800-555-0100", "contactType": "sales"},
                {
                    "@type": "ContactPoint",
                    "telephone": "+1-800-555-0200",
                    "contactType": "support",
                    "email": "support@example.com",
                },
            ],
        }
    )
    out = json_to_markdown_rows(payload)
    assert "+1-800-555-0100" in out
    assert "+1-800-555-0200" in out
    assert "support@example.com" in out
    assert "sales" in out
    assert "support" in out


def test_oversized_contact_point_array_is_capped() -> None:
    entries = [{"telephone": f"+1-800-555-{i:04d}"} for i in range(25)]
    payload = _payload({"@type": "Organization", "name": "Acme Corp", "contactPoint": entries})
    out = json_to_markdown_rows(payload)
    rendered = sum(1 for i in range(25) if f"+1-800-555-{i:04d}" in out)
    assert rendered == 10


def test_scalar_list_fields_are_unaffected() -> None:
    payload = _payload({"@type": "Product", "name": "Widget", "keywords": ["a", "b", "c"]})
    out = json_to_markdown_rows(payload)
    assert "- **keywords:** a, b, c" in out
