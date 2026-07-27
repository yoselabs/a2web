## MODIFIED Requirements

### Requirement: Extractor supports an opt-in request_routing mode

`Extractor.extract` SHALL accept a `request_routing: bool = False` keyword argument. When `True`, the extractor SHALL use the `EXTRACT_ROUTER_V1` template (instead of the default `EXTRACT_CACHEABLE_V1`), append the router-shape JSON schema documentation and worked examples to `parts.system` (NEVER to `parts.cache_prefix`), parse the structured JSON addendum from the model response, and populate `ExtractionResult.routing: RouterPayload | None`. Only the per-call question (`"Question: {ask}"`) lives in `parts.tail` — the schema/examples text is static (independent of `content` and `ask`) and therefore lives in the cacheable `system` bucket alongside the general instructions, not in the always-resent `tail`.

When `request_routing=False`, `ExtractionResult.routing` SHALL be `None` and the existing `EXTRACT_CACHEABLE_V1` template path SHALL be used with no behavioral change.

**The router path SHALL request exactly one output contract.** When `request_routing=True`, the extractor SHALL NOT append the next-links fence suffix, regardless of the value of `request_next_links`. The router schema's `other_pages` field already covers link discovery; appending the fence suffix asks the model for a SECOND, differently-shaped contract (`[{anchor, url, reason, kind}]` in a fenced block "AFTER your answer") that directly contradicts the router prompt's "Output strict JSON only", and is what caused models to emit prose-plus-fence instead of the JSON envelope. `request_routing` SHALL take precedence over `request_next_links` in prompt construction, and the two flags being simultaneously `True` SHALL be a supported, tested combination — not an unreachable one.

The `EXTRACT_ROUTER_V1` template SHALL share `cache_prefix_template` byte-equality with `EXTRACT_CACHEABLE_V1` so the cache-prefix discipline survives — the two prompts differ only in `system` and `tail_template`.

The router-shape system prompt SHALL:
- Declare the closed-enum vocabulary for `structural_form` (9 values), `shape` (7 values), and `obstacle` (4 values, optional).
- Instruct the model to omit `obstacle` on healthy pages.
- Instruct the model to emit `also_here` and `other_pages` only when populated — empty arrays acceptable but soft-discouraged via a "context decides count, 3 good 5 great" rule.
- Instruct the model that `also_here` MUST index only on-page content the answer left unreturned, emitted as terse query-grammar strings (ADR-0015).
- Instruct the model that an `other_pages` `drilldown` `reason` MUST be question-conditioned (WHY this URL likely has what's missing) and ≤120 chars.

#### Scenario: request_routing=False preserves existing extraction shape

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=False)` is awaited
- **THEN** the model receives the existing `EXTRACT_CACHEABLE_V1` prompt and `ExtractionResult.routing` is `None`

#### Scenario: request_routing=True populates the routing field

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=True)` is awaited against a content page and the model returns a well-formed JSON router-shape addendum
- **THEN** `ExtractionResult.routing` is a `RouterPayload` instance with `answer`, `structural_form`, `shape` populated, plus any of `obstacle` / `also_here` / `other_pages` that the model included

#### Scenario: The router path never requests a next-links fence

- **WHEN** `Extractor.extract(..., request_routing=True, request_next_links=True)` is awaited — the combination `query` uses in production
- **THEN** the rendered prompt contains NO next-links fence instruction and NO `{"anchor": ..., "url": ...}` exemplar; the model is asked for the router JSON envelope only

#### Scenario: Cache-prefix integrity survives the new template

- **WHEN** `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` is called for any `X` and any `Y1`, `Y2`
- **THEN** the resulting `PromptParts.cache_prefix` is byte-identical for `(X, Y1)` and `(X, Y2)` — the per-call variation lives entirely in `tail`

### Requirement: Router-shape parsing tolerates malformed JSON and omitted optional fields

The `Extractor` SHALL parse the router-shape JSON from the model response using a fence-tolerant parser (accepting raw JSON or `\`\`\`json` fenced blocks). When parsing fails, `ExtractionResult.routing` SHALL be `None`, an operator-relevant log message SHALL be emitted, and the extraction call SHALL otherwise succeed (`answer` SHALL still be returned via the existing extraction path).

**A parse failure SHALL NOT return the raw model response as `answer`.** The returned `answer` SHALL be sanitized: any fenced block (`\`\`\`next_links`, `\`\`\`json`, or an unlabelled fence whose body parses as JSON) SHALL be stripped from the answer text before it is returned, on the routing path as well as the non-routing path. The fence-stripping discipline SHALL NOT be reachable only via the `request_next_links` branch — a stray fence emitted on the routing path SHALL be stripped with equal force. Returning un-contracted model scaffolding in the single field every caller parses is a wire-contract violation regardless of which branch produced it.

**A lost routing payload SHALL be observable, not silent.** When `request_routing=True` and parsing fails, the extraction SHALL emit the `llm_wobble` structured log event (per the shared wobble discipline) and SHALL record the loss on `ExtractionResult.routing_lost`, distinguishing it from `routing is None` on a call that never requested routing.

Surfacing that loss on the ASK ENVELOPE (a hint and/or a confidence cap) is explicitly OUT OF SCOPE here and deferred. A first attempt fired on every `query` whose model did not return a router envelope — the common case, including across the frozen wire goldens — which would have made a warning-severity hint permanent background noise and traded one wire defect for another. The signal is recorded and logged so the decision can be made on evidence later; it is not yet wire-visible.

When the parsed payload omits any of the optional fields (`obstacle`, `ask_here`, `try_url`), the boundary type SHALL accept the omission (defaults to `None` for `obstacle`; empty tuples for `ask_here` and `try_url`).

When the parsed payload contains an `obstacle` value, the model SHOULD still populate `structural_form` and `shape` with best-guess values; if the model omits them on an obstacle page, the boundary parser SHALL leave `ExtractionResult.routing` as `None` (the obstacle is recorded via the standard fetch-failure path instead).

#### Scenario: Malformed JSON leaves routing None

- **WHEN** the extractor receives a model response with malformed JSON in the router-shape block
- **THEN** `ExtractionResult.routing` is `None` and `ExtractionResult.answer` still carries the successfully parsed answer text

#### Scenario: A parse failure never leaks a fence into the answer

- **WHEN** `request_routing=True` and the model returns prose followed by a `\`\`\`next_links` fenced JSON array, so the router envelope parse raises `ParseError`
- **THEN** `ExtractionResult.answer` carries the prose ONLY, with the fenced block and its delimiters removed, and contains no `\`\`\`next_links` substring

#### Scenario: A lost routing payload is logged and recorded

- **WHEN** `request_routing=True` and the router envelope parse fails
- **THEN** exactly one `llm_wobble` event is emitted with `boundary="routing"`, and `ExtractionResult` records that routing was requested and lost

#### Scenario: Healthy page with no obstacle or follow-ups omits all three optionals

- **WHEN** the model returns a router-shape payload with `obstacle`, `ask_here`, `try_url` all absent
- **THEN** the boundary type constructs successfully with `obstacle=None`, `ask_here=()`, `try_url=()`
