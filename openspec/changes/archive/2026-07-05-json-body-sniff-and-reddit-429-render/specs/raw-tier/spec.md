## ADDED Requirements

### Requirement: JSON body served under a non-JSON content-type is recovered

The raw tier SHALL sniff a 2xx response body whose content-type is not JSON-family: if the body parses as a JSON document, the tier SHALL normalize the returned `TierResult.content_type` to `application/json` and set `Verdict.ok`, so the orchestrator synthesizes it in-place (json-endpoint-direct-routing) instead of running trafilatura over JSON or escalating to the jina HTML reader (both of which mangle it into a false `length_floor`).

The sniff SHALL be prefix-guarded — only a body opening with `{` or `[` (checked within a bounded leading window, never a full-body `lstrip`) is decoded and parsed — so large HTML/binary bodies are never decoded. Because real HTML never parses as a JSON document, the sniff SHALL only ever upgrade a genuine JSON body; a non-JSON body is left untouched.

The parse SHALL go through the `json_in_script` package's `sniff_json_body`, keeping the json-loads-funnel invariant intact (no new `json.loads` in the tier).

#### Scenario: JSON served as text/html is normalized to application/json

- **WHEN** the raw tier receives an HTTP 200 with `content-type: text/html` but a body that parses as JSON (e.g. `{"items": [{"title": "A"}]}`)
- **THEN** the returned `TierResult.verdict == Verdict.ok` and `TierResult.content_type == "application/json"`

#### Scenario: JSON served as text/plain is normalized

- **WHEN** the raw tier receives an HTTP 200 with `content-type: text/plain` and a JSON body
- **THEN** `TierResult.content_type` is normalized to `application/json` (verdict `ok`), not left as a `content_type_mismatch`

#### Scenario: A genuine HTML page is not mis-sniffed

- **WHEN** the raw tier receives an HTTP 200 `text/html` page with an HTML body (`<html>…`)
- **THEN** `TierResult.content_type` stays `text/html` and the body is not treated as JSON

#### Scenario: A binary body is never decoded

- **WHEN** the raw tier receives a body opening with non-`{`/`[` bytes (e.g. a PDF `%PDF-…`)
- **THEN** the sniff short-circuits on the prefix guard without decoding or parsing the body
