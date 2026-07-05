## ADDED Requirements

### Requirement: JSON responses are synthesized in-place, never routed through jina

When a tier returns a 2xx response whose content-type is JSON-family (per the shared `_is_json_content_type` predicate), the orchestrator SHALL treat the JSON body as content: the tier wins (`Verdict.ok`), and `_phase_extract` SHALL synthesize the JSON body to markdown instead of running trafilatura. The orchestrator SHALL NOT escalate a JSON response to the jina (`r.jina.ai`) HTML reader.

Synthesis SHALL proceed as: parse the body via `json_in_script.parse_json_response`; on a `JsonPayload`, render via `domain.json_to_markdown_rows`; install the result as `fc.pre_rendered_payload` so the quality gate's content-type check is bypassed and trafilatura is skipped.

#### Scenario: A JSON API endpoint is synthesized, not escalated

- **WHEN** the raw tier returns HTTP 200 + `application/json` for `https://api.example.com/data` carrying `{"items": [{"title": "A"}, {"title": "B"}]}`
- **THEN** the fetch succeeds with `status == ok`, `content_md` contains the synthesized rows, and no diagnostic records a `jina` tier step

#### Scenario: A recognized JSON shape renders as a table/records

- **WHEN** a JSON response body carries a top-level `products` array of objects with `name` + `price`
- **THEN** `content_md` is the `json_to_markdown_rows` rendering (linked records / table), identical to the JSON-in-script path for the same shape

### Requirement: Unknown-shape JSON falls back to the JSON text, never a false failure

When `json_to_markdown_rows` produces nothing for a parseable JSON body (a shape it does not recognize), the orchestrator SHALL fall back to the JSON text itself as `content_md` — pretty-printed and length-capped — so a valid-but-unrecognized JSON payload reaches the caller and the `ask` extractor. A JSON response SHALL NOT produce a `length_floor` failure on account of the jina HTML reader, and SHALL NOT be silently dropped.

#### Scenario: An unrecognized JSON shape still returns content

- **WHEN** a JSON response body is a valid document of a shape `json_to_markdown_rows` does not recognize (e.g. `{"weather": {"temp": 21, "wind": 4}}`)
- **THEN** `content_md` contains the pretty-printed JSON (length-capped), `status == ok`, and the fetch is not a `length_floor` failure

#### Scenario: A small-but-complete JSON response bypasses the thin-shell length floor

- **WHEN** a JSON response body is a small complete document below the length floor (e.g. `{"count": 42}`)
- **THEN** the quality gate accepts it (`status == ok`) — the length-floor exemption keys strictly on the JSON content-type, not on length or pre-rendered status, so HTML SPA shells keep the full floor
