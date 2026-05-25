## Why

When an agent calls `ask(url, question)`, the server-side Haiku extraction already touches the entire page — yet the caller learns nothing about *what else the page offers*: what kind of content it is, how richly it was extracted, what other questions it could answer, what structural shapes (lists, code, citations, timelines) are present. The agent must either guess, re-fetch with a different question, or escalate blindly.

Four spike rounds (`eval/findings_2026-05-24-affordances-{v1,v2-v3,v5-two-axes}.md` plus the v6 name-bench) confirm that a single extraction call can also emit a structured **affordances** field at ~$0.002/URL marginal cost (~18% on top of the existing extraction). The 30-URL × 3-variant benchmark locked the prompt shape (V_CTX_V3), the two-axis rubric (`page_kind_confidence` + `content_value`), the envelope discipline (omit content_value / shapes / follow_ups on obstacle pages), the closed page_kind / shape vocabularies, and the field name (`affordances`, scored highest behavioral grounding 2.67/5 vs `signals`/`hints`/`leads`).

Design is fully locked. This change wires it through.

## What Changes

- **BREAKING (additive)** — `AskResponse` gains an `affordances: AffordancesPayload | None` field. None on opt-out; populated on every successful extraction when default-on `include_affordances=True`. Existing parsers that ignore unknown fields are unaffected.
- **BREAKING (additive)** — the `ask` tool gains an `include_affordances: bool = True` kwarg. Default ON — consumer decides whether to use the data; a2web's job is to surface signal.
- New module `src/a2web/packages/llm_extract/affordances.py` with frozen-dataclass boundary types `AffordancesPayload` + `AffordanceShape` (package-side; no domain imports).
- New domain-side pydantic model `AffordancesPayload` (and `AffordanceShape`) in `src/a2web/models.py` at module scope.
- New prompt template `EXTRACT_WITH_AFFORDANCES_V1` in `src/a2web/packages/llm_extract/prompts.py` — extends `EXTRACT_CACHEABLE_V1`'s tail (NOT the cached prefix, so byte-stable cache discipline survives). Embeds the V_CTX_V3 prompt from `eval/spikes/affordances_v5_two_axes.py` plus a `G_commerce: {listing, product-page, package-page}` cluster trigger (pre-ship fix for the v5 Amazon miscalibration).
- `Extractor.extract(..., request_affordances: bool = False)` — when true, appends the affordances request to `parts.tail` (cache_prefix stays stable) and parses a structured JSON addendum from the response. Mirrors the existing `request_next_links` pattern.
- `LlmExtractorResource` selects template based on the flag.
- `fetcher.fetch(..., include_affordances: bool = True)` threads the flag from the router down to the extractor.
- `build_ask_response` projects the package-side `AffordancesPayload` into the pydantic model at the domain seam.
- Closed enums (typed Literals) for `page_kind` (28 values: 24 content + 4 obstacle), `page_kind_confidence` (low/medium/high), `content_value` (low/medium/high — only emitted on content pages), and shape `label` (8 values).

## Capabilities

### New Capabilities

(none — affordances extend existing capabilities rather than introducing new ones)

### Modified Capabilities

- `ask-response`: response envelope gains the optional `affordances` field with closed-enum sub-fields and envelope-discipline rules (omit content_value/shapes/follow_up_questions when page_kind is an obstacle kind).
- `extraction`: extractor surfaces a new optional `request_affordances` path that uses `EXTRACT_WITH_AFFORDANCES_V1`, parses the structured addendum, and propagates a typed `AffordancesPayload` boundary on `ExtractionResult`. Cache-prefix integrity preserved (schema example lives in tail).

## Impact

### Code

- `src/a2web/packages/llm_extract/affordances.py` (new) — boundary types + closed enums (string literals in the package; the typed-Literal pydantic mirrors live in `models.py`).
- `src/a2web/packages/llm_extract/prompts.py` — new `EXTRACT_WITH_AFFORDANCES_V1` constant; the existing `EXTRACT_CACHEABLE_V1` stays untouched.
- `src/a2web/packages/llm_extract/extractor.py` — `extract()` gains `request_affordances` kwarg; new helper to parse the affordances JSON addendum from the response tail; `ExtractionResult` gains `affordances: AffordancesPayload | None`.
- `src/a2web/packages/llm_extract/__init__.py` — export new boundary types + template.
- `src/a2web/llm_resource.py` — pick template based on flag; pass through to `Extractor.extract`.
- `src/a2web/models.py` — pydantic `AffordancesPayload` + `AffordanceShape`; `AskResponse.affordances` field; serializer drops field when None (envelope discipline).
- `src/a2web/fetcher.py` — pass `include_affordances` through; populate `FetchResponse.affordances` (internal field).
- `src/a2web/fetcher_response.py` — project boundary type → pydantic in `build_ask_response`.
- `src/a2web/routers.py` — `ask` tool gains `include_affordances` kwarg with documentation.

### Tests

- `tests/packages/llm_extract/test_affordances_parse.py` (new) — boundary-type parsing, malformed JSON handling, envelope discipline on obstacle pages.
- `tests/capabilities/ask_response/test_affordances_wire.py` (new) — full path through `ask`, opt-out via `include_affordances=False`, default-on behavior, obstacle page suppression on the wire.
- Existing extractor/extraction tests gain `request_affordances=False` defaults — no behavioral change.

### Wire / MCP clients

- `AskResponse` envelope grows. Clients that ignore unknown fields are unaffected. Clients that strictly enumerate fields will need to widen their parser — flagged in the changelog.

### Cost / performance

- Default-on adds ~500 completion tokens per `ask` call (~$0.002, ~18%). Opt-out via `include_affordances=False` preserves the lean v0.14 envelope shape and the current cost.

### Backlog cleanup

- Removes the "🟡 Affordances production wiring" item.
- Keeps the "🟢 Corpus refresh" (already done in this change's prep) and "🟢 Content-value second-order signal" items for future work.

### Out of scope (deferred to BACKLOG)

- Content-value second-order escalation (auto-browser-tier on `content_value=low`).
- Affordances on `fetch_raw` (stays minimal — no LLM).
- Confidence calibration beyond the `G_commerce` cluster.
- Telemetry on affordances field usage in production.
