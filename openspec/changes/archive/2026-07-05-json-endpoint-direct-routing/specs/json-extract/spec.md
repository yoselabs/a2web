## ADDED Requirements

### Requirement: Detect a whole-response JSON body

The `json_in_script` extractor SHALL provide `parse_json_response(text: str) -> JsonPayload | None` that parses an entire response body as a single top-level JSON document and returns a `JsonPayload(source="generic", data=<parsed>, script_id=None, byte_size=<len(text)>)`. On any parse failure it SHALL return `None` (never raise), so the orchestrator can fall back to normal handling.

This function SHALL own `json.loads` for the response-body path (as `extract_json_payloads` already owns it for the in-script path), keeping the architecture's json-loads funnel invariant intact — no `json.loads` call is added outside the `json_in_script` package.

The emitted `source="generic"` payload SHALL route through the existing `json_to_markdown_rows` synthesis (which already handles `generic`), so a top-level `{"products": [...]}`, `{"items": [...]}`, or bare array of objects renders to markdown with no new domain code.

#### Scenario: A JSON object response parses to a generic payload

- **WHEN** `parse_json_response('{"products": [{"name": "Widget", "price": "9.99"}]}')` is called
- **THEN** it returns a `JsonPayload(source="generic", data={"products": [...]}, script_id=None, byte_size=<n>)`

#### Scenario: A JSON array response parses to a generic payload

- **WHEN** `parse_json_response('[{"title": "A"}, {"title": "B"}]')` is called
- **THEN** it returns a `JsonPayload(source="generic", data=[...], script_id=None)`

#### Scenario: A non-JSON body returns None

- **WHEN** `parse_json_response('<html>not json</html>')` is called
- **THEN** it returns `None` (no raise)

#### Scenario: A truncated / malformed JSON body returns None

- **WHEN** `parse_json_response('{"a": 1,')` is called
- **THEN** it returns `None` (no raise)
