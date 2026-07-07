## MODIFIED Requirements

### Requirement: Multi-source extraction escalation ladder

After `extract_markdown` returns, `_phase_extract` SHALL run an ordered ladder of structured-extraction sources **unconditionally** — there is no recall trigger gating entry to the ladder. Each rung self-gates: it produces output only when its own preconditions hold — `json_in_script` only when embedded JSON is present; structural record extraction only when a record region clears the `record-extraction` detection guards. The ladder runs in order: (1) trafilatura prose (the baseline, always present when extraction ran); (2) `json_in_script` payloads (embedded JSON, including JSON-LD); (3) structural record extraction via the `record-extraction` capability. The ladder SHALL **collect every rung that produces output** into an immutable `fc.content_candidates: list[ContentCandidate]` in that fixed source order — it SHALL NOT stop at the first passing rung and SHALL NOT gate collection on a length/quality replace check. When no structured rung produces output, `fc.content_candidates` SHALL still carry the trafilatura prose candidate. Each rung SHALL emit `StageStarted` / `StageEnded` LDD events naming the source.

`ContentCandidate` SHALL carry a typed `answer_bearing: bool` field (a plain field on the existing `dataclass(slots=True, frozen=True)` — NOT a `dict[str, Any]` bag). The `json_synth` rung SHALL set `answer_bearing = is_answer_bearing(payload)` (the `json-extract` package predicate — `True` for a strong ld_json / microdata payload). The trafilatura and `record_synth` rungs SHALL set `answer_bearing = False`. This flag is the single signal the quality-gate exemption and the display pick consult; no consumer re-derives schema strength.

#### Scenario: Ladder runs without a trigger

- **WHEN** `extract_markdown` returns for any page
- **THEN** the escalation ladder runs, each rung self-gates on its own preconditions, and every rung that produces output contributes a `ContentCandidate` to `fc.content_candidates`

#### Scenario: All producing sources are collected, none discarded on length

- **WHEN** the raw HTML carries both embedded JSON and a detectable record region
- **THEN** `fc.content_candidates` carries the trafilatura, `json_synth`, and `record_synth` candidates together — no rung is dropped because another was longer

#### Scenario: Server-rendered listing reaches record extraction

- **WHEN** the raw HTML is a server-rendered listing with no embedded JSON
- **THEN** the `json_in_script` source yields nothing and the structural record-extraction source runs, contributing its candidate alongside the prose candidate

#### Scenario: Article reaches the record rung and it self-gates

- **WHEN** the page is a genuine article
- **THEN** the structural record-extraction rung runs, returns no record set, and `fc.content_candidates` carries only the trafilatura prose candidate

#### Scenario: Strong JSON-LD candidate is tagged answer-bearing

- **WHEN** the `json_synth` rung renders a strong `LocalBusiness` / `Product` payload (`is_answer_bearing` → `True`)
- **THEN** the resulting `ContentCandidate` has `answer_bearing == True`, while the sibling trafilatura prose candidate has `answer_bearing == False`

#### Scenario: Weak JSON-LD candidate is not tagged answer-bearing

- **WHEN** the `json_synth` rung renders a weak payload (a 2-field `Organization`, or an `opengraph`-only payload)
- **THEN** the resulting `ContentCandidate` has `answer_bearing == False`

### Requirement: Quality-aware content replacement

The single-source, length-proxy replace rule is **retired**. The extractor SHALL be fed the full menu of collected candidates, and the wire `content_md` default SHALL be chosen by quality, not rendered length.

**Extractor input (the menu).** When `ask=` is set, `_phase_extract_answer` SHALL assemble `fc.content_candidates` into one deterministic menu string and pass it as `extract(content=menu)`. Assembly SHALL be a **pure function of the candidate list**: fixed source ordering, static content-free section labels, and no timestamps, counts, object identity, or dict-iteration-order dependence — so the menu for a given fetched page is byte-identical across repeated asks (preserving the `cache_prefix = {content}` prompt-cache invariant). Before assembly, the deterministic side SHALL apply **coarse subset-suppression only** — a candidate whose normalized text is a strict substring of another's is dropped; finer (semantic) dedup is the LLM's responsibility. When the assembled menu exceeds `max_content_chars`, trimming SHALL be **priority-ordered** (prose and `json_synth` trimmed last, `record_synth` first), never a blind uniform truncation.

**Wire default (`content_md`).** `fc.content_md` SHALL be set to a single candidate chosen by quality: the trafilatura prose candidate when non-empty, else the first structured candidate, else (when a handler/archive/browser produced `fc.pre_rendered_payload`) that pre-rendered payload. Rendered length SHALL NOT be the selector. The wire *shape* of `content_md` is unchanged (a single markdown string).

**Answer-bearing structured beats sub-floor prose for display.** When the quality-picked prose candidate is present but **below `LENGTH_FLOOR`** AND an `answer_bearing` structured candidate exists, `fc.content_md` SHALL surface the answer-bearing structured candidate instead of the sub-floor prose. This ensures `fetch_raw` (which returns only `content_md`, not the menu) carries the structured answer rather than a thin nav/footer fragment. Above-floor prose is unaffected — it remains the display pick. The menu fed to the extractor is unchanged (it always carried every candidate).

#### Scenario: The extractor receives every collected source

- **WHEN** a page yields prose plus a `json_synth` payload carrying the answer that is shorter than the prose
- **THEN** the menu fed to the extractor contains the `json_synth` payload (it is NOT dropped for being shorter), so the model can answer from it

#### Scenario: Menu assembly is byte-stable across asks

- **WHEN** the same fetched page is extracted for two different `ask` values
- **THEN** the assembled menu string (and thus the prompt `cache_prefix`) is byte-identical for both, so the prompt-cache and extraction-cache still hit

#### Scenario: Budget trim is priority-ordered

- **WHEN** the assembled menu exceeds `max_content_chars`
- **THEN** the `record_synth` candidate is trimmed before the prose and `json_synth` candidates, never all sources uniformly

#### Scenario: Subset candidates are suppressed before assembly

- **WHEN** one candidate's normalized text is a strict substring of another candidate's text
- **THEN** the subset candidate is dropped from the menu, guarding against the same payload duplicated across microdata / og / ld_json / records

#### Scenario: Wire content_md is prose-preferred, not longest

- **WHEN** a page yields a trafilatura prose candidate and a longer `record_synth` candidate
- **THEN** the wire `content_md` surfaces the prose candidate (quality pick), while the menu fed to the extractor still carries both

#### Scenario: A good article is never clobbered

- **WHEN** the page is an article
- **THEN** the record-extraction guards reject it, no record set is produced, and both the menu and the wire `content_md` keep trafilatura's output

#### Scenario: Contact page display surfaces the structured answer over sub-floor prose

- **WHEN** a contact page yields a sub-floor trafilatura prose candidate (e.g. a 180-char footer) alongside an `answer_bearing` `LocalBusiness` `json_synth` candidate carrying phone + email
- **THEN** the wire `content_md` surfaces the `LocalBusiness` structured candidate (so `fetch_raw` returns the phone + email), not the thin footer prose

#### Scenario: Above-floor prose still wins display over structured

- **WHEN** a page yields an above-`LENGTH_FLOOR` prose candidate and an `answer_bearing` structured candidate
- **THEN** the wire `content_md` surfaces the prose candidate — the answer-bearing override fires only when the prose is sub-floor

### Requirement: JSON-LD single-entity rendering is default-keep, not an allowlist

Single-entity JSON-LD rendering (`Product` / `Article` / `NewsArticle` / `Recipe`, plus the entity/answer schemas `LocalBusiness` / `Organization` / `ContactPoint` / `Event`, and the like) SHALL render answer-bearing fields by **default-keep**: every key whose value is a scalar or a shallow dict/list of scalars SHALL be surfaced, in the entity's own field order, EXCEPT a fixed **noise denylist** — JSON-LD machinery (`@context`, `@type`, `@id`, `@graph`), image/media URLs (`image`, `thumbnail`, `thumbnailUrl`, `logo`), `mainEntityOfPage`, and values exceeding a length cap (so a full article body is not dumped into a key-value line). The renderer's entity-type dispatch SHALL cover the answer/entity schemas (`LocalBusiness`, `Organization`, `ContactPoint`, `Event`) alongside the commerce/editorial types, so a contact page's `LocalBusiness` renders its `telephone` / `email` / `address` rather than producing an empty string. The renderer SHALL NOT gate fields against a fixed allowlist of "interesting" keys; an answer-bearing field the author did not anticipate (e.g. a `Product.gtin`, a `Recipe.recipeYield`) SHALL still be surfaced. This eliminates the value-blind structural-filter projection (ADR-0003 / ADR-0004).

#### Scenario: An unanticipated answer-bearing field is surfaced

- **WHEN** a JSON-LD entity carries a scalar field outside any prior fixed allowlist (e.g. `gtin13`, `recipeYield`)
- **THEN** `json_to_markdown_rows` includes that field's key and value in the rendered entity

#### Scenario: Known noise is dropped

- **WHEN** a JSON-LD entity carries `@type`, `@context`, `image`, and a 5,000-character `articleBody`
- **THEN** the rendered entity omits the `@`-prefixed keys, the image URL, and the oversized body, while keeping the entity's short answer-bearing scalars

#### Scenario: A LocalBusiness entity renders its contact fields

- **WHEN** `json_to_markdown_rows` is given an `ld_json` payload holding a `LocalBusiness` with `name`, `telephone`, `email`, `url`
- **THEN** the rendered markdown is non-empty and contains the `telephone` and `email` values (previously it rendered to an empty string because the type was outside the dispatch allowlist)
