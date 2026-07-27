## MODIFIED Requirements

### Requirement: Router-shape parsing tolerates malformed JSON and omitted optional fields

The `Extractor` SHALL parse the router-shape JSON from the model response using a fence-tolerant parser (accepting raw JSON or `\`\`\`json` fenced blocks). Fence tolerance SHALL NOT be removed on the assumption that the model obeys the prompt's "Output strict JSON only" clause: across 15 live extractions the model wrapped its response in a `\`\`\`json` fence 100% of the time, so the fence path is the ONLY path in practice.

When parsing fails, `ExtractionResult.routing` SHALL be `None`, an operator-relevant log message SHALL be emitted, and the extraction call SHALL otherwise succeed (`answer` SHALL still be returned via the existing extraction path).

**A parse failure SHALL NOT return the raw model response as `answer`.** The returned `answer` SHALL be sanitized: any fenced block (`\`\`\`next_links`, `\`\`\`json`, or an unlabelled fence whose body parses as JSON) SHALL be stripped from the answer text before it is returned, on the routing path as well as the non-routing path. Returning un-contracted model scaffolding in the single field every caller parses is a wire-contract violation regardless of which branch produced it.

**A missing classification SHALL NOT discard a supplied index.** When the parsed envelope carries a valid `answer` but omits or malforms `structural_form` or `shape`, the boundary parser SHALL still populate `also_here` and `other_pages` from the envelope. Only the consumers that genuinely require the classification — specifically the DOM-mined options shelf — SHALL be suppressed. Discarding an index the model actually supplied, because an unrelated field was absent, is a direct ADR-0015 harm: `query` withholds the body by default, so the index is the caller's only remaining view of what was withheld.

**A lost routing payload SHALL be observable as a TYPED outcome, not a boolean.** `ExtractionResult` SHALL carry a `RoutingOutcome` distinguishing at minimum: `recovered`; `unparsable` (no envelope recovered even after wobble tolerance); `unclassified` (envelope recovered, classification absent); and `provider_error` (the provider raised, so no response text existed to parse). The boolean `routing_lost` SHALL be REMOVED, not retained alongside the typed value.

The `provider_error` arm SHALL NOT produce an index-loss hint: it is already reported independently via `ExtractionResult.provider_error` and the `ask_unanswered` path, and attributing a total extraction failure to the index would double-report one event as two.

Routing loss SHALL NOT promote the response to `status: failed` or set `retrieval_incomplete`. Status describes RETRIEVAL; hints describe extraction degradation. The only extraction event that earns `failed` is the absence of an answer, which `ask_unanswered` already owns. A response carrying a good answer SHALL NOT be failed because its metadata degraded.

#### Scenario: Malformed JSON leaves routing None

- **WHEN** the extractor receives a model response with malformed JSON in the router-shape block
- **THEN** `ExtractionResult.routing` is `None`, `ExtractionResult.answer` still carries the successfully parsed answer text, and `ExtractionResult.routing_outcome` is `unparsable`

#### Scenario: A parse failure never leaks a fence into the answer

- **WHEN** `request_routing=True` and the model returns prose followed by a `\`\`\`next_links` fenced JSON array, so the router envelope parse raises `ParseError`
- **THEN** `ExtractionResult.answer` carries the prose ONLY, with the fenced block and its delimiters removed, and contains no `\`\`\`next_links` substring

#### Scenario: A missing classification preserves the supplied index

- **WHEN** the model returns a valid envelope carrying `answer`, `also_here` with 3 entries, and `other_pages` with 2 entries, but omits `structural_form`
- **THEN** the resulting payload retains all 3 `also_here` entries and both `other_pages` entries, `routing_outcome` is `unclassified`, and the DOM-mined options shelf is suppressed

#### Scenario: A provider error is not reported as an index loss

- **WHEN** the provider raises and the extraction substitutes an empty completion
- **THEN** `routing_outcome` is `provider_error`, `ExtractionResult.provider_error` is populated, and NO index-loss operator hint is emitted

#### Scenario: Routing loss never fails a response that carries an answer

- **WHEN** `request_routing=True`, the envelope is unrecoverable, and a non-empty `answer` survives sanitization
- **THEN** the response `status` is unchanged (not `failed`), `retrieval_incomplete` is not set by this condition, and the degradation is reported via an operator hint only

#### Scenario: A fenced envelope is recovered, not rejected

- **WHEN** the model returns a well-formed router envelope wrapped in a `\`\`\`json` fence — the observed behaviour on 100% of live calls
- **THEN** the routing payload is recovered and `routing_outcome` is `recovered`

### Requirement: LLM boundary parsing uses an explicit wobble-tolerance policy

Every parser in the codebase that consumes LLM-returned JSON SHALL declare an explicit per-field wobble-tolerance policy drawn from a closed vocabulary: `STRICT` (raise on missing/malformed), `DERIVE` (compute from already-parsed fields), `DEFAULT` (substitute a sentinel for a field that was PRESENT but malformed), `OPTIONAL` (the field is legitimately omissible; substitute the documented empty value), and `SKIP` (return `None` or an empty collection for the boundary or per-entry as documented).

**An absent optional field SHALL NOT be reported as a wobble.** The `OPTIONAL` tolerance exists to separate two facts the previous four-value vocabulary conflated: *the field was absent, which is normal* versus *the field was present but malformed, so a default was substituted*. Only the second is a recovery worth an operator's attention. A structured log event that fires on a healthy call is not a signal, and SHALL NOT be emitted: prior to this change a fully-recovered extraction emitted five `llm_wobble` warnings — one for each of `obstacle`, `also_here`, `other_pages`, `refinement_axes`, `item_total_seen` — on 100% of successful calls, rendering the key unusable for detecting anything.

When any field's policy fires AND the policy is not `OPTIONAL`, the parser SHALL emit a single structured log event with key `llm_wobble` and the fields `boundary`, `field`, `policy_applied`, `model`, and a bounded `raw_excerpt` (≤ 200 chars).

The discipline module SHALL remain domain-independent — it SHALL NOT import from `a2web.<domain>`.

The migration sites SHALL adopt the discipline per the policy table documented in `design.md`. In particular:

- `Judge.score` SHALL treat `reached` as `DERIVE`. Other judge fields (`scores`, `overall`) SHALL remain `STRICT`; `reasoning` SHALL be `DEFAULT`.
- The router-shape policy SHALL classify the genuinely optional envelope fields — `obstacle`, `also_here`, `other_pages`, `refinement_axes`, `item_total_seen` — as `OPTIONAL`.
- `Extractor._split_answer_and_routing` SHALL NO LONGER skip the whole routing payload when `structural_form` or `shape` is missing; it SHALL salvage the payload per the decoupling requirement above.
- `_project_routing` in `src/a2web/fetcher_response.py` SHALL keep its `SKIP`-on-closed-enum-violation behaviour under the `llm_wobble` key.

#### Scenario: An omitted optional field emits no wobble event

- **WHEN** the model returns a valid envelope carrying only `answer`, `structural_form`, and `shape`, omitting all five optional fields
- **THEN** the routing payload is recovered and ZERO `llm_wobble` events are emitted

#### Scenario: A malformed optional field still emits a wobble event

- **WHEN** the model returns an envelope whose `also_here` is a string rather than a list
- **THEN** the field is recovered to its documented empty value and exactly one `llm_wobble` event fires with `field="also_here"`

#### Scenario: STRICT policy raises on missing required field

- **WHEN** `Judge.score` receives a model response missing `scores`
- **THEN** `JudgeParseError` is raised and no `llm_wobble` log event is emitted

#### Scenario: DERIVE policy recovers missing `reached` from `overall`

- **WHEN** `Judge.score` receives a model response containing `scores`, `overall=4`, `reasoning`, but no `reached`
- **THEN** the returned `JudgeVerdict.reached` is `True`, `JudgeVerdict.raw` carries `reached_derived: True`, and one `llm_wobble` event fires with `policy_applied="derive"`

#### Scenario: Discipline module respects packages-independence

- **WHEN** `tests/test_packages_independence.py` walks the wobble discipline module
- **THEN** zero imports from `a2web.<domain>` modules are detected
