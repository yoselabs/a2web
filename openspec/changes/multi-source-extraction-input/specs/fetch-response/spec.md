## MODIFIED Requirements

### Requirement: timing, cache, diagnostics, and tokens are debug-only on FetchResponse

`FetchResponse` SHALL expose all debug-tier observability through a single `debug` sub-object, not as scattered top-level keys. The `debug` object SHALL carry `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, and `content_candidates`. The `content_candidates` entry SHALL be the list of extraction-input candidates the page produced — each rendered as `{source, content_md}` — exposing exactly the menu the server-side extractor was fed. The `debug` key SHALL appear on the wire only when `fetch_raw` (or `ask`) is called with `debug=True`; with `debug=False` it SHALL be absent. No `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `content_candidates` key SHALL appear at the top level of the envelope. `content_candidates` SHALL remain a flat attribute on the model for internal callers; only the wire serializer regroups it under `debug`.

#### Scenario: default fetch_raw omits the debug sub-object

- **WHEN** `fetch_raw` is called with `debug=False`
- **THEN** the wire payload contains no `debug` key, and no `started_at`, `total_ms`, `cache`, `diagnostics`, `tokens`, or `content_candidates` key at the top level

#### Scenario: debug fetch_raw nests the full trace under debug

- **WHEN** `fetch_raw` is called with `debug=True`
- **THEN** the wire payload contains a `debug` object carrying `started_at`, `total_ms`, `cache`, `tokens`, the `diagnostics` trace, and `content_candidates`

#### Scenario: content_candidates surfaces the extractor menu

- **WHEN** `fetch_raw` is called with `debug=True` against a page that produced multiple extraction candidates
- **THEN** the `debug.content_candidates` list carries one `{source, content_md}` entry per candidate fed to the extractor, in the menu's source order
