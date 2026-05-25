## ADDED Requirements

### Requirement: State construction goes through a single bootstrap factory

The codebase SHALL expose exactly one async factory `bootstrap_state(settings: AppSettings) -> tuple[AppState, Resources]` in `src/a2web/state.py`. `Resources` SHALL be a frozen dataclass carrying the three Lazy-eligible resources (`browser_pool: BrowserPool`, `llm_extractor: LlmExtractorResource`, `cookie_jar: CookieJarResource`).

Production composition (`server.py`), eval harness (`llm_eval/__main__.py`), and test fixtures (`tests/conftest.py::make_default_state`) SHALL all delegate to this factory. Direct manual construction of `BrowserPool` / `LlmExtractorResource` / `CookieJarResource` outside the factory is forbidden.

A new resource added to the bundle SHALL automatically appear in all three construction paths without per-path edits.

#### Scenario: Production composition uses bootstrap_state

- **WHEN** `server.py` builds the App's provider chain
- **THEN** the resources come from `bootstrap_state(...)`, not from individual ad-hoc constructors

#### Scenario: Eval harness wires browser_pool via bootstrap_state

- **WHEN** `llm_eval/__main__.py` constructs systems for the bench
- **THEN** `BrowserPool` reaches `A2WebDetail` and `A2WebExtract` via the factory's `Resources` bundle, not via a manually constructed pool that could be forgotten (preventing the class of regression that caused the v0.22 bench gap)

#### Scenario: Tests bypass DI but still use the factory

- **WHEN** `tests/conftest.py::make_default_state` is invoked
- **THEN** it returns the `(AppState, Resources)` tuple from `bootstrap_state`, with stubs as needed for resources that tests want to omit

### Requirement: FetchContext exposes Lazy[T] resources as non-optional

`FetchContext.browser_pool`, `FetchContext.llm_extractor`, and `FetchContext.cookie_jar` SHALL be declared as `Lazy[BrowserPool]`, `Lazy[LlmExtractorResource]`, `Lazy[CookieJarResource]` respectively — NO `| None` union. When a direct-call path does not provision a real resource, the caller SHALL pass a stub Lazy whose invocation raises a `ResourceUnavailable` exception carrying an operator-hint-ready reason string.

Phases that consume these resources SHALL NOT check `if fc.<resource> is not None`; instead they SHALL `await fc.<resource>()` and catch `ResourceUnavailable` to emit the operator hint path.

#### Scenario: Production tool invocation passes real Lazy

- **WHEN** WebRouter.ask is invoked through the MCP transport
- **THEN** all three Lazy[T] params resolve to real resources via a2kit DI; no `None` check is required at the phase seam

#### Scenario: Eval harness stub raises operator-hint-ready error when no real pool

- **WHEN** an eval system runs with `Resources(browser_pool=stub)` and a phase awaits the stub
- **THEN** the stub raises `ResourceUnavailable("eval harness not provisioned with BrowserPool")` which the phase catches and converts to `OperatorHint(code="browser_unavailable", ...)`

### Requirement: Verdict is the pure projection of the decision log

`FetchContext.gate_verdict` and `FetchContext.gate_subsystem` (mutable snapshot slots) SHALL be removed. All code that previously read them SHALL read from `fc.resolved_verdict()` or a new pure projection helper `fc.last_gate_outcome() -> GateOutcomeProjection | None` that derives the most recent gate observation from the log.

The decision log (`fc.observations`) remains the single mutable accumulator; the verdict and gate state are pure projections — they cannot diverge from the log.

#### Scenario: Re-gate after browser escalation reflects the new verdict

- **WHEN** a browser escalation completes and `_regate_after_escalation` appends a new `gate_outcome` observation
- **THEN** the subsequent call to `fc.resolved_verdict()` returns the verdict reflecting the new observation, with no separate `gate_verdict` field to keep in sync

#### Scenario: Cache-write gate reads the projection, not a snapshot

- **WHEN** `_phase_cache_write` evaluates whether to write the body to cache
- **THEN** it checks `fc.resolved_verdict() is Verdict.ok` (the projection); no parallel snapshot exists that could disagree

### Requirement: Extraction pipeline returns immutable candidates and selects via a pure function

`_phase_extract` and the extraction escalation ladder (`_run_extraction_escalation`, `_escalate_via_json`, `_escalate_via_records`) SHALL produce `ContentCandidate` values (`@dataclass(frozen=True, slots=True)` with fields `source: Literal["trafilatura","json_synth","record_synth","browser_rerun"]`, `content_md: str`, `headings: list[Heading]`, `links: list[Link]`, `score: int`) instead of mutating `fc.content_md` in place.

Selection across candidates SHALL be performed by a pure function `pick_best(candidates: list[ContentCandidate]) -> ContentCandidate | None` carrying the existing length-aware-for-flat and threading-aware-for-records policy. The orchestrator assigns `fc.content_md` = `pick_best(...).content_md` exactly once per phase invocation, not interleaved with mutation.

#### Scenario: Trafilatura + JSON + record candidates are all generated, best is picked

- **WHEN** `_phase_extract` runs on a record-set-shaped page where trafilatura produces 1500 chars, json_synth produces 0, and record_synth produces 3000 (threaded)
- **THEN** all three `ContentCandidate` instances exist as immutable values, and `pick_best` returns the record_synth candidate; `fc.content_md` is assigned once to that candidate's content_md

#### Scenario: Browser escalation re-runs extraction purely

- **WHEN** a browser escalation produces new raw HTML and the orchestrator re-invokes the extraction pipeline
- **THEN** a fresh list of `ContentCandidate` is generated against the new HTML; the prior `fc.content_md` is replaced (not amended) with the new pick_best result

