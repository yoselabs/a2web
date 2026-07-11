## MODIFIED Requirements

### Requirement: ask returns the lean AskResponse envelope

The primary extraction tool SHALL be named `query` (renamed from `ask`) and SHALL take a `query` parameter (renamed from `question`) carrying the caller's information need. The tool SHALL keep its bare canonical name via `canonical_name_override="query"` (the flat `web_query` name is NOT the installed contract). The tool SHALL return an `AskResponse` model, distinct from the `FetchResponse` returned by `fetch_raw`. `AskResponse` SHALL always carry `confidence` and the answer field; these required fields SHALL never be omitted from the wire. `status`, `tier`, and `url` each appear only when they deviate from their default and are governed by their own requirements.

The `query` parameter's tool description SHALL teach the query grammar (per the `Follow-up suggestions render as queries` requirement) so the caller phrases their own input as a concrete query, not a full sentence, in ≤ ~50 words.

#### Scenario: query success carries the answer and required fields

- **WHEN** `query` completes successfully against a fixture page with an information need
- **THEN** the returned envelope is an `AskResponse` with `confidence` and the answer field populated

#### Scenario: tool advertises the bare name

- **WHEN** the MCP `list_tools` is served
- **THEN** the primary extraction tool is advertised as `query` (not `ask`, not `web_query`)

### Requirement: AskResponse carries router-shape fields by default

The `AskResponse` envelope SHALL carry the same-URL follow-up field under the name `refine` (renamed from `ask_here`) — a `list[str]` of follow-up **queries**, omitted from the wire when empty. `refine` items SHALL be query-grammar strings (per `Follow-up suggestions render as queries`), NOT full questions. All other router-shape field behaviour is unchanged.

#### Scenario: refine replaces ask_here on the wire

- **WHEN** `query` returns a routing payload with a populated follow-up list
- **THEN** the wire carries `refine` (never `ask_here`) as a list of query-grammar strings

#### Scenario: empty refine is omitted

- **WHEN** the routing payload's follow-up list is empty
- **THEN** the wire carries no `refine` key (and no `ask_here` key under any circumstance)

## ADDED Requirements

### Requirement: Follow-up suggestions render as queries

`refine` items SHALL be emitted as **queries**, defined by deletion: the verb frame ("does it" / "are there any" / "do any reviews mention") and the already-known page entity SHALL be dropped; the target noun(s) and the single discriminating operator SHALL be kept. Permitted operators are only free-prior ones — `,` (list), `vs` (contrast), `/` (alternatives), quotes (exact), `-` (exclude) — plus CAPS on at most one load-bearing token. A trailing `?` SHALL appear only when the item asks the tool to *judge / determine which* (DECIDE), not to *retrieve* (FIND). A follow-up that would require `and` SHALL be split into two `refine` items.

#### Scenario: a fork survives as a query

- **WHEN** a follow-up discriminates between two poles (e.g. Apple-Home-specific vs universal)
- **THEN** the `refine` item keeps the `vs` operator and drops the verb frame — e.g. `connection issues: Apple Home only vs all platforms`

#### Scenario: a compound is split

- **WHEN** a follow-up joins two distinct asks with `and`
- **THEN** it is emitted as two separate `refine` items, not one `and`-joined string

#### Scenario: a qualifier is preserved and emphasized

- **WHEN** a follow-up hinges on a qualifier (e.g. *official* / *documented*)
- **THEN** the qualifier is kept and MAY be CAPS-marked — e.g. `OFFICIAL troubleshooting / known issues for pairing`
