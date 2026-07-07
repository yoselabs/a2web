# extraction Specification

## Purpose
TBD - created by archiving change pr3-raw-tier. Update Purpose after archive.
## Requirements
### Requirement: Trafilatura markdown extraction

The system SHALL provide `async extract_markdown(html: str, url: str) -> ExtractResult` in `src/a2web/extract/trafilatura_ext.py`. The implementation SHALL call trafilatura's `extract` with markdown output and run synchronously inside `asyncio.to_thread`. `ExtractResult` SHALL be a `@dataclass(slots=True)` carrying `content_md: str`, `title: str | None`, `byline: str | None`, `headings: list[Heading]`, `links: list[Link]`, `score: float | None`. Trafilatura blocking calls SHALL NOT appear outside this module's `_extract_sync` helper.

#### Scenario: Sync chokepoint per ASYNC lint

- **WHEN** ruff scans `src/a2web/extract/trafilatura_ext.py`
- **THEN** ASYNC100/210/230 emits zero diagnostics

#### Scenario: Markdown output for a well-formed article fixture

- **WHEN** `extract_markdown(html=<blog post fixture>, url=<fixture url>)` is awaited
- **THEN** the result has non-empty `content_md`, a non-empty `title`, and at least one `Heading`

### Requirement: htmldate publication and update dates

The system SHALL provide `async find_published(html: str, url: str) -> date | None` and `async find_updated(html: str, url: str) -> date | None` in `src/a2web/extract/htmldate_ext.py`. Both SHALL wrap htmldate sync calls via `asyncio.to_thread`. Returning `None` (no detectable date) SHALL be a normal outcome, never an exception.

#### Scenario: Date present

- **WHEN** `find_published` is awaited on a fixture with `<meta property="article:published_time">`
- **THEN** the returned value is a `datetime.date` matching the fixture

#### Scenario: Date absent

- **WHEN** `find_published` is awaited on a fixture with no date markers
- **THEN** the returned value is `None`

### Requirement: OpenGraph + Twitter + JSON-LD metadata

The system SHALL provide `parse_metadata(html: str) -> dict[str, str]` in `src/a2web/extract/metadata.py` as a pure synchronous function. It SHALL extract `og:*`, `twitter:*` meta tags and the first JSON-LD block (`<script type="application/ld+json">`), flattened with dot-keys: `og.type`, `og.image`, `twitter.card`, `jsonld[0].author`, `jsonld[0].datePublished`, etc. Missing fields SHALL be omitted from the dict (no `None` values).

#### Scenario: OG type and image extraction

- **WHEN** `parse_metadata(html)` is called on a fixture with `<meta property="og:type" content="article">` and `<meta property="og:image" content="https://x/y.jpg">`
- **THEN** the returned dict contains `og.type == "article"` and `og.image == "https://x/y.jpg"`

#### Scenario: JSON-LD author and date

- **WHEN** `parse_metadata(html)` is called on a fixture with a JSON-LD `Article` carrying `author` and `datePublished`
- **THEN** the returned dict contains `jsonld[0].author` and `jsonld[0].datePublished`

### Requirement: max_content_chars override flows from CLI / MCP to the extractor

The `Extractor.__init__` already accepts `max_content_chars: int = 100_000`. The orchestrator SHALL accept an optional `max_content_chars: int | None` parameter on `fetch()` that overrides the default for a single call. The CLI SHALL expose this as `--max-content-chars INT` on both `ask` and `fetch_raw` tools (also surfaced as an Annotated kwarg on the MCP tools). When the override is `None` or absent, the existing 100,000-char default applies. When set, the override SHALL be plumbed through `FetchContext.max_content_chars` to `LlmExtractorResource.extract()` to `Extractor.extract()`'s truncation step.

#### Scenario: CLI flag caps content before extraction

- **WHEN** a caller invokes `a2web web ask --url <yandex-market-url> --question <q> --max-content-chars 50000` against a page whose raw markdown is 345 KB
- **THEN** the prompt sent to the extractor model contains at most 50,000 chars of content (plus the truncation marker), and the `tokens.full` field on the response reflects the capped count

#### Scenario: Default behavior preserved when flag absent

- **WHEN** a caller invokes `a2web web ask --url <url> --question <q>` without the new flag
- **THEN** the existing 100,000-char default applies; no behavior change from the pre-fix release

#### Scenario: MCP kwarg matches CLI flag

- **WHEN** an MCP client calls the `fetch` tool with `max_content_chars=50000`
- **THEN** the same cap applies; the MCP tool schema documents the kwarg via `Annotated[int | None, pydantic.Field(description=...)]`

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

### Requirement: JSON-LD ItemList synthesis

The synthetic-markdown adapter `json_to_markdown_rows` SHALL render a JSON-LD `ItemList` payload — an `itemListElement` array of `ListItem` entries — into record rows. For each list item the adapter SHALL lift commerce fields out of nested objects before rendering: `offers.price` combined with `offers.priceCurrency` into a single price token (e.g. `3690 TRY`), `offers.url` into the row url, and `aggregateRating.ratingValue` into a rating. A row's top-level scalar `price`/`url` (flat-shaped payloads) SHALL pass through unchanged. `json_in_script` already detects `ld_json` payloads and `rank_payloads` already prefers `ItemList`; this requirement closes the synthesis gap so a detected `ItemList` becomes usable `content_md`.

Commerce-shaped lists — rows where at least half carry a lifted `price` or `url` — SHALL render as linked markdown records, one per item: `- [<name>](<url>) — <price> ⭐ <rating>`, with `price` and `rating` omitted when absent and a plain name used when no url is present. The product url SHALL appear verbatim and un-truncated (the linked-record form is not subject to the fixed-width table's per-cell character cap), so downstream router-shape extraction can cite it as a `try_url` drilldown. The synthetic `image` field SHALL NOT be emitted for listing rows. Link text SHALL be sanitized so item names containing `]`, `)`, or newlines cannot break the markdown link.

Non-commerce `ItemList` payloads — rows carrying neither a lifted `price` nor `url` — SHALL keep the existing fixed-width markdown table rendering, unchanged.

#### Scenario: Product ItemList renders to linked records with price and url

- **WHEN** a thin page carries a JSON-LD `ItemList` whose `itemListElement` entries are `Product` items with `offers.{price, priceCurrency, url}`
- **THEN** `json_to_markdown_rows` renders one linked-record line per item, each carrying the item name as link text, the full un-truncated product url as the link target, and a combined `<price> <currency>` token (e.g. `3690 TRY`); no image-CDN url appears in the output

#### Scenario: Long product url is preserved verbatim

- **WHEN** a `Product` item's `offers.url` exceeds the fixed-width table's 80-character cell cap
- **THEN** the rendered linked record contains the complete url with no truncation

#### Scenario: aggregateRating is lifted when present

- **WHEN** a `Product` item carries `aggregateRating.ratingValue`
- **THEN** the rendered record includes the rating; items without a rating render without one and are not malformed

#### Scenario: Non-commerce ItemList keeps table rendering

- **WHEN** an `ItemList` carries rows that have neither a lifted `price` nor `url` (e.g. a generic index list)
- **THEN** `json_to_markdown_rows` renders the existing fixed-width markdown table, not linked records

#### Scenario: Empty ItemList yields no rows

- **WHEN** the `ItemList` is empty or malformed
- **THEN** the adapter yields no rows and the ladder continues to the next source

### Requirement: Extractor supports an opt-in request_routing mode

`Extractor.extract` SHALL accept a `request_routing: bool = False` keyword argument. When `True`, the extractor SHALL use the `EXTRACT_ROUTER_V1` template (instead of the default `EXTRACT_CACHEABLE_V1`), append the router-shape JSON schema to `parts.tail` (NEVER to `parts.cache_prefix`), parse the structured JSON addendum from the model response, and populate `ExtractionResult.routing: RouterPayload | None`.

When `request_routing=False`, `ExtractionResult.routing` SHALL be `None` and the existing `EXTRACT_CACHEABLE_V1` template path SHALL be used with no behavioral change.

The `EXTRACT_ROUTER_V1` template SHALL share `cache_prefix_template` byte-equality with `EXTRACT_CACHEABLE_V1` so the cache-prefix discipline survives — the two prompts differ only in their `tail_template`.

The router-shape tail prompt SHALL:
- Declare the closed-enum vocabulary for `structural_form` (9 values), `shape` (7 values), `genre` (7 values, optional), and `obstacle` (4 values, optional).
- Instruct the model to omit `genre` when no value clearly applies.
- Instruct the model to omit `obstacle` on healthy pages.
- Instruct the model to emit `ask_here` and `try_url` only when populated — empty arrays acceptable but soft-discouraged via a "context decides count, 3 good 5 great" rule.
- Instruct the model that `ask_here` MUST emit only questions whose answer requires reading the body (no obvious-from-title questions).
- Instruct the model that `try_url[*].reason` MUST be question-conditioned (WHY this URL likely has what's missing) and ≤120 chars.

#### Scenario: request_routing=False preserves existing extraction shape

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=False)` is awaited
- **THEN** the model receives the existing `EXTRACT_CACHEABLE_V1` prompt and `ExtractionResult.routing` is `None`

#### Scenario: request_routing=True populates the routing field

- **WHEN** `Extractor.extract(content=..., ask=..., request_routing=True)` is awaited against a content page and the model returns a well-formed JSON router-shape addendum
- **THEN** `ExtractionResult.routing` is a `RouterPayload` instance with `answer`, `structural_form`, `shape` populated, plus any of `genre` / `obstacle` / `ask_here` / `try_url` that the model included

#### Scenario: Cache-prefix integrity survives the new template

- **WHEN** `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` is called for any `X` and any `Y1`, `Y2`
- **THEN** the resulting `PromptParts.cache_prefix` is byte-identical for `(X, Y1)` and `(X, Y2)` — the per-call variation lives entirely in `tail`

#### Scenario: Cache-prefix byte-identical to EXTRACT_CACHEABLE_V1

- **WHEN** both `EXTRACT_ROUTER_V1.render(content=X, ask=Y)` and `EXTRACT_CACHEABLE_V1.render(content=X, ask=Y)` are called
- **THEN** their `cache_prefix` strings are byte-identical (assertable via `test_prompt_cache_stability.py`)

### Requirement: RouterPayload boundary type lives in packages/llm_extract

`RouterPayload` SHALL be a frozen dataclass with `slots=True` declared in `src/a2web/packages/llm_extract/router_payload.py`. It SHALL carry these fields:

- `answer: str`
- `structural_form: str` (string at the package boundary; the pydantic mirror enforces the 9-value closed enum at the domain seam)
- `shape: str` (string at the package boundary; the pydantic mirror enforces the 7-value closed enum)
- `genre: str | None` (optional, `None` when none applies)
- `obstacle: str | None` (optional, `None` on healthy pages)
- `ask_here: tuple[str, ...]` (empty tuple by default)
- `try_url: tuple[NextUrlBoundary, ...]` (empty tuple by default)

`NextUrlBoundary` SHALL be a frozen dataclass carrying `url: str` and `reason: str`.

The module SHALL NOT import from `a2web.<domain>` (enforced by `tests/test_packages_independence.py`). Boundary-to-pydantic projection happens at the domain seam in `src/a2web/fetcher_response.py`.

#### Scenario: RouterPayload is frozen dataclass with slots

- **WHEN** an instance is constructed
- **THEN** the instance has `__slots__`, is `frozen=True`, and attempting to mutate any field raises `dataclasses.FrozenInstanceError`

#### Scenario: Package independence preserved

- **WHEN** `tests/test_packages_independence.py` walks `src/a2web/packages/llm_extract/router_payload.py`
- **THEN** zero imports from `a2web.<domain>` modules are detected

### Requirement: Router-shape parsing tolerates malformed JSON and omitted optional fields

The `Extractor` SHALL parse the router-shape JSON from the model response using a fence-tolerant parser (accepting raw JSON or `\`\`\`json` fenced blocks). When parsing fails, `ExtractionResult.routing` SHALL be `None`, an operator-relevant log message SHALL be emitted, and the extraction call SHALL otherwise succeed (`answer` SHALL still be returned via the existing extraction path).

When the parsed payload omits any of the optional fields (`genre`, `obstacle`, `ask_here`, `try_url`), the boundary type SHALL accept the omission (defaults to `None` for `genre` and `obstacle`; empty tuples for `ask_here` and `try_url`).

When the parsed payload contains an `obstacle` value, the model SHOULD still populate `structural_form` and `shape` with best-guess values; if the model omits them on an obstacle page, the boundary parser SHALL leave `ExtractionResult.routing` as `None` (the obstacle is recorded via the standard fetch-failure path instead).

#### Scenario: Malformed JSON leaves routing None

- **WHEN** the extractor receives a model response with malformed JSON in the router-shape block
- **THEN** `ExtractionResult.routing` is `None` and `ExtractionResult.answer` still carries the successfully parsed answer text

#### Scenario: Healthy page with no obstacle or follow-ups omits all four optionals

- **WHEN** the model returns a router-shape payload with `genre`, `obstacle`, `ask_here`, `try_url` all absent
- **THEN** the boundary type constructs successfully with `genre=None`, `obstacle=None`, `ask_here=()`, `try_url=()`

### Requirement: Claude Code provider isolates MCP servers, subagents, and surfaces num_turns

The `ClaudeCodeProvider` SHALL pass `mcp_servers={}`, `strict_mcp_config=True`, and `agents={}` to `ClaudeAgentOptions` in addition to the existing `setting_sources=[]`, `skills=[]`, and `extra_args={"disable-slash-commands": None}` opt-outs. This SHALL prevent the host Claude Code CLI's MCP server config (including memory-bearing MCP servers) from contaminating the extraction call.

The provider SHALL surface `num_turns` from `ResultMessage.raw` so callers can verify the `max_turns=1` cap held in production.

#### Scenario: MCP servers and subagents are explicitly disabled

- **WHEN** `ClaudeCodeProvider.complete` is awaited
- **THEN** the `ClaudeAgentOptions` instance has `mcp_servers={}`, `strict_mcp_config=True`, and `agents={}` set, regardless of the host CLI's MCP config

#### Scenario: num_turns surfaces in the response raw blob

- **WHEN** `ClaudeCodeProvider.complete` returns
- **THEN** `ProviderResponse.raw["num_turns"]` is present and equals 1 (matching the `max_turns=1` cap)

### Requirement: Judge parser tolerates a missing `reached` field by deriving it from `overall`

`Judge._parse_verdict_json` SHALL accept judge responses that omit (or set to `null`) the `reached` field when `scores`, `overall`, and `reasoning` are all present and well-typed. In that case the parser SHALL derive `reached = (overall >= 3)`, MUST emit a `structlog` warning named `judge_reached_missing` carrying the model name, the parsed `overall`, and the derived value, and MUST populate `JudgeVerdict.raw["reached_derived"] = True`. The verdict SHALL otherwise round-trip identically to a verdict where the model returned `reached` explicitly.

`Judge` SHALL continue to raise `JudgeParseError` when any of `scores`, `overall`, or `reasoning` is missing or malformed, and when `reached` is present but not coercible to `bool`. The derivation path SHALL only apply when `reached` is absent from the parsed JSON or explicitly `null`.

Eval consumers (`src/a2web/llm_eval/runner.py`) SHALL treat a derived verdict as a successful judgment: `row.judge_error` SHALL remain `None`, `row.judge_reached` SHALL carry the derived `bool`, and the row SHALL count toward the system's reach-rate aggregation in `src/a2web/llm_eval/report.py`.

#### Scenario: Model omits `reached` on an otherwise well-formed verdict

- **WHEN** the judge LLM returns `{"scores":[5,3,5], "overall":4, "reasoning":"..."}` with no `reached` key
- **THEN** `Judge.score` returns a `JudgeVerdict` with `overall=4`, `scores=[5,3,5]`, `reached=True`, `raw["reached_derived"]=True`, and a `judge_reached_missing` warning is emitted

#### Scenario: Model returns `reached: null` on an otherwise well-formed verdict

- **WHEN** the judge LLM returns `{"scores":[1,0], "overall":1, "reached": null, "reasoning":"miss"}`
- **THEN** `Judge.score` returns a `JudgeVerdict` with `reached=False` (derived from `overall=1 < 3`), `raw["reached_derived"]=True`, and a `judge_reached_missing` warning is emitted

#### Scenario: Fully-formed verdict still round-trips unchanged

- **WHEN** the judge LLM returns `{"scores":[5,5], "overall":5, "reached": true, "reasoning":"ok"}`
- **THEN** `Judge.score` returns a `JudgeVerdict` with `reached=True`, `raw["reached_derived"]` is absent (or falsy), and no `judge_reached_missing` warning is emitted

#### Scenario: Missing `overall` still raises `JudgeParseError`

- **WHEN** the judge LLM returns `{"scores":[5], "reasoning":"x"}` with no `overall` and no `reached`
- **THEN** `Judge.score` raises `JudgeParseError` carrying the raw text — derivation requires a parsed `overall`

#### Scenario: Missing `reasoning` still raises `JudgeParseError`

- **WHEN** the judge LLM returns `{"scores":[5], "overall":5}` with no `reached` and no `reasoning`
- **THEN** `Judge.score` raises `JudgeParseError` — the derivation branch only rescues `reached`, not `reasoning`

#### Scenario: Eval row records a derived verdict as a successful judgment

- **WHEN** a benchmark cell receives a verdict whose `reached` was derived
- **THEN** the resulting row carries `judge_error=None`, `judge_reached` set to the derived bool, and `judge_overall` populated; the run report counts the row toward the system's reach rate

### Requirement: LLM boundary parsing uses an explicit wobble-tolerance policy

Every parser in the codebase that consumes LLM-returned JSON SHALL declare an explicit per-field wobble-tolerance policy drawn from a closed vocabulary of four values: `STRICT` (raise on missing/malformed), `DERIVE` (compute from already-parsed fields), `DEFAULT` (substitute a sentinel), `SKIP` (return `None` or an empty collection for the boundary or per-entry as documented). The policy SHALL live in a shared discipline module under `src/a2web/packages/llm_extract/` and SHALL be imported by every LLM-touching parser in the project.

The discipline module SHALL be domain-independent — it SHALL NOT import from `a2web.<domain>` (enforced by `tests/test_packages_independence.py`).

When any field's policy fires (i.e. the field is missing or malformed and a non-STRICT policy applies), the parser SHALL emit a single structured log event with key `llm_wobble` and the fields `boundary`, `field`, `policy_applied`, `model`, and a bounded `raw_excerpt` (≤ 200 chars). The legacy log keys (`routing_validation_failed`, `judge_failed`, `clarity_judge_failed`, `next_links_judge_failed`, and any silent-drop paths) SHALL be retired in favour of this single key.

The four migration sites SHALL adopt the discipline per the policy table documented in `design.md`. In particular:

- `Judge.score` SHALL treat `reached` as `DERIVE` (computed as `overall >= 3` when missing or null), retiring the current `JudgeParseError` raise for that specific field. Other judge fields (`scores`, `overall`) SHALL remain `STRICT`; `reasoning` SHALL be `DEFAULT` (empty string).
- `Extractor._split_answer_and_routing` SHALL keep its current behavior (`SKIP` the whole routing payload when `structural_form` or `shape` is missing), expressed via the shared discipline.
- `_project_routing` in `src/a2web/fetcher_response.py` SHALL keep its current behavior (`SKIP` the whole projected `RouterPayload` on closed-enum violation), expressed via the shared discipline; the log key SHALL change from `routing_validation_failed` to `llm_wobble`.
- `BenchJudge.score_clarity` and `BenchJudge.score_next_links` SHALL treat the numeric score as `STRICT` and `reasoning` as `DEFAULT` (empty string).

No public API SHALL change: `JudgeVerdict`, `ExtractionResult`, `RouterPayload`, `ClarityVerdict`, and `NextLinksVerdict` shapes are preserved.

#### Scenario: STRICT policy raises on missing required field

- **WHEN** `Judge.score` receives a model response missing `scores`
- **THEN** `JudgeParseError` is raised and no `llm_wobble` log event is emitted (the error path carries its own diagnostics)

#### Scenario: DERIVE policy recovers missing `reached` from `overall`

- **WHEN** `Judge.score` receives a model response containing `scores`, `overall=4`, `reasoning`, but no `reached` (the 2026-05-25 `wikipedia-rust / a2web_extract` trace)
- **THEN** the returned `JudgeVerdict.reached` is `True` (derived from `overall >= 3`), `JudgeVerdict.raw` carries `reached_derived: True`, no `JudgeParseError` is raised, and one `llm_wobble` log event fires with `boundary="judge"`, `field="reached"`, `policy_applied="derive"`

#### Scenario: DEFAULT policy substitutes sentinel for missing non-critical field

- **WHEN** `BenchJudge.score_clarity` receives a model response with `clarity=4` but no `reasoning`
- **THEN** the returned `ClarityVerdict.reasoning` is `""`, no `JudgeParseError` is raised, and one `llm_wobble` event fires with `boundary="bench_clarity"`, `field="reasoning"`, `policy_applied="default"`

#### Scenario: SKIP policy drops the whole boundary payload while sibling data survives

- **WHEN** `Extractor._split_answer_and_routing` receives a model response with a valid `answer` but missing `structural_form`
- **THEN** the returned tuple is `(answer, None)` — the `RouterPayload` is dropped but `answer` survives — and one `llm_wobble` event fires with `boundary="extractor_routing"`, `field="structural_form"`, `policy_applied="skip"`

#### Scenario: Closed-enum violation in `_project_routing` emits the unified log key

- **WHEN** `_project_routing` receives a package-side `RouterPayload` with `shape="something_not_in_literal_7"`
- **THEN** the function returns `None`, the answer-bearing caller is unaffected, and a single `llm_wobble` event fires with `boundary="fetcher_routing_mirror"`, `field="shape"`, `policy_applied="skip"` (replacing the legacy `routing_validation_failed` key)

#### Scenario: Discipline module respects packages-independence

- **WHEN** `tests/test_packages_independence.py` walks `src/a2web/packages/llm_extract/wobble.py`
- **THEN** zero imports from `a2web.<domain>` modules are detected

### Requirement: JSON-LD Recipe synthesis

The synthetic-markdown adapter `json_to_markdown_rows` SHALL render a JSON-LD `Recipe` payload (an entry whose `@type` is `Recipe`, single or within `@graph`) into answer-bearing markdown. It SHALL surface the recipe name (as a heading), `description`, `recipeYield`, the time fields (`prepTime` / `cookTime` / `totalTime`), the `recipeIngredient` list, and — critically — the `nutrition` (`NutritionInformation`) subobject rendered as a readable labelled line carrying its present fields (`calories`, `sugarContent`, `fatContent`, `carbohydrateContent`, `proteinContent`, etc.). Rendering SHALL be content-agnostic (no number/unit special-casing — it renders whichever nutrition fields are present), defensive against shape variance (`nutrition` absent, `recipeInstructions` as `HowToStep[]` vs string, lists vs scalars), and SHALL omit fields it cannot read without raising. A `Recipe` whose `nutrition.calories` is `"268 calories"` SHALL produce output containing `268 calories`.

#### Scenario: Recipe nutrition reaches the synthetic surface

- **WHEN** a page carries a JSON-LD `Recipe` with `nutrition: {@type: NutritionInformation, calories: "268 calories", sugarContent: "24 grams sugar"}`
- **THEN** `json_to_markdown_rows` renders a Recipe block whose text contains `268 calories` and `24 grams sugar`

#### Scenario: Recipe without nutrition still renders

- **WHEN** a `Recipe` payload has no `nutrition` field
- **THEN** the adapter renders the recipe's other answer-bearing fields (name, ingredients, times) and omits the nutrition line, without raising

#### Scenario: Recipe is no longer dropped

- **WHEN** the only answer-bearing JSON-LD payload on a page is a `Recipe`
- **THEN** `json_to_markdown_rows` returns non-empty output (previously a `Recipe` matched no branch and yielded an empty string)

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

