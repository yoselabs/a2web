## MODIFIED Requirements

### Requirement: ask returns the lean AskResponse envelope

The primary extraction tool SHALL be named `query` (renamed from `ask`) and SHALL take a `query` parameter (renamed from `question`). The tool's wire name SHALL be the literal string passed to its `@mcp.tool(name="query")` registration in `src/a2web/routers.py`; there is no override mechanism — the name in source IS the wire name. The tool SHALL return an `AskResponse` model, distinct from the `FetchResponse` returned by `fetch_raw`. `AskResponse` SHALL NOT declare `fit_md`, `tokens`, `is_user_authored`, or `original_url`. `AskResponse` SHALL always carry `confidence` and the answer field (`answer`); these required fields SHALL never be omitted from the wire. `status`, `tier`, and `url` each appear only when they deviate from their default and are governed by their own requirements. The `query` parameter's tool description SHALL teach the query grammar (per `Follow-up suggestions render as queries`) and SHALL state the cost asymmetry (per `also_here and other_pages are governed by the withheld-body index`).

#### Scenario: tool advertises the bare name

- **WHEN** the MCP `list_tools` is served
- **THEN** the primary extraction tool is advertised as `query` (not `ask`, not `web_query`)

#### Scenario: ask success carries the answer and required fields

- **WHEN** `query` completes successfully against a fixture page with a query
- **THEN** the returned envelope is an `AskResponse` with `confidence` and `answer` populated, and has no `fit_md`, `tokens`, `is_user_authored`, or `original_url` field

#### Scenario: ask never exposes fit_md or is_user_authored

- **WHEN** any `query` invocation completes
- **THEN** the serialized wire payload contains no `fit_md` and no `is_user_authored` key
