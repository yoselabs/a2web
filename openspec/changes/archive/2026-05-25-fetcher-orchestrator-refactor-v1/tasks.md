## Phase 1 — Unify state construction

- [x] 1.1 Create `Resources` frozen dataclass in `src/a2web/state.py` carrying `browser_pool: BrowserPool`, `llm_extractor: LlmExtractorResource`, `cookie_jar: CookieJarResource`.
- [x] 1.2 Add `async def bootstrap_state(settings: AppSettings) -> tuple[AppState, Resources]` in `state.py` that constructs the four AppState resources + the three Lazy-eligible resources via their existing constructors.
- [x] 1.3 Refactor `server.py` provider registrations: per-resource `build_*` factories moved into `state.py` so `server.py` and `bootstrap_state` share them — production providers retain `Lazy[T]` first-use semantics (bootstrap returns cheap unstarted instances, framework's `__aenter__` still fires on first DI resolution).
- [x] 1.4 Refactor `llm_eval/__main__.py` to call `bootstrap_state(settings)` instead of manually building each resource. Pass `Resources` bundle into `A2WebDetail` / `A2WebExtract` constructors; they pull `browser_pool` / `llm_extractor` from the bundle.
- [x] 1.5 Refactor `tests/conftest.py`: `make_default_state` delegates to the shared `build_*` factories; sibling `make_default_bundle` returns `(AppState, Resources)` for tests that need the Lazy-eligible half.
- [x] 1.6 Update `A2WebDetail.__init__` / `A2WebExtract.__init__` signatures to accept `resources: Resources` instead of individual `browser_pool=` / `extractor=` kwargs.
- [x] 1.7 Run `make check` — 780 tests pass, coverage 88.99%. `make bench` deferred to end-of-phase batch (user-triggered, live network).

## Phase 2 — Decision-log-only verdict

- [x] 2.1 Add `last_gate_outcome(self) -> GateOutcomeProjection | None` method on `FetchContext` — scans `self.observations` in reverse for the latest `gate_outcome` kind and returns a frozen projection (`verdict`, `subsystem`, `suggested_tier` fields). Adds `subsystem: str | None` to `Observation` so the projection has its data.
- [x] 2.2 Remove `FetchContext.gate_verdict` and `FetchContext.gate_subsystem` fields.
- [x] 2.3 Replace remaining reads via local-bind `gate_outcome = fc.last_gate_outcome()` in `fetcher_response.build_response` (ty's narrowing across separate calls is conservative — single bind is cleaner).
- [x] 2.4 In `_phase_gate_and_escalate`, deleted the snapshot assignments. The new gate observation carries verdict + subsystem + suggested_tier — Diagnostic / StageEnded read `gate_result` directly, captcha check reads `gate_result.subsystem`.
- [x] 2.5 `_regate_after_escalation` deleted the snapshot assignments; passes `subsystem` to `observe()` so the new observation is the new gate state.
- [x] 2.6 `fetcher_response.build_response` derives `gate_subsystem` once from `last_gate_outcome()`, threads into both narrative + diagnostics summary builders.
- [x] 2.7 `make check` — 780 tests pass, coverage 88.99%. `make bench` deferred to end-of-phase batch.

## Phase 3 — Lazy[T] non-optionality + stub-on-unavailable

- [x] 3.1 Added `unavailable_lazy(resource_cls, *, reason) -> Lazy[T]` in `state.py` — returns an async thunk raising `ResourceUnavailable(reason)`.
- [x] 3.2 Added `class ResourceUnavailable(RuntimeError)` in `state.py` carrying `reason: str`.
- [x] 3.3 `FetchContext.browser_pool` / `llm_extractor` / `cookie_jar` now annotated `Lazy[T]` (no `| None`), defaulted via `field(default_factory=lambda: unavailable_lazy(...))`.
- [x] 3.4 `fetch()` kwargs kept as `Lazy[T] | None = None` for caller convenience; normalized to `unavailable_lazy(...)` at the entrypoint before constructing FetchContext. Phases never see `None`.
- [x] 3.5 `make_default_bundle` (sibling of `make_default_state`) already returns the real cheap-to-construct resources from `bootstrap_state`'s factories. Tests that need the unavailable semantics use the fetch() default (omit the kwarg).
- [x] 3.6 No direct-call test paths needed updating — fetch()'s None-normalization preserves the prior implicit-unavailable behavior.
- [x] 3.7 `_escalate_browser`, `_phase_extract_answer`, `_phase_resolve_cookies`, `_phase_cookies_staleness` switched from `if fc.<resource> is not None` to `try/except ResourceUnavailable`. Operator-hint path now carries the reason string from the unavailable Lazy.
- [x] 3.8 `make check` — 780 tests pass, coverage 88.98%.

## Phase 4 — Typed EscalationSignal

- [x] 4.1 Created `src/a2web/packages/escalation.py` (moved out of `actions/` per packages-independence rule — `block_detector.py` produces it, so the type must be package-owned). Carries `NextTier = Literal["browser","tls_impersonate","archive"]` + frozen `EscalationSignal(next_tier, reason)`.
- [x] 4.2 `decision_log.Observation`: swapped `suggested_tier: str | None` → `escalation: EscalationSignal | None`.
- [x] 4.3 `block_detector.BlockResult`: swapped field + all `evaluate()` branches now build typed `EscalationSignal(next_tier=..., reason=<subsystem>)`.
- [x] 4.4 `fetcher._GateResult` + `evaluate()` thread `escalation: EscalationSignal | None` instead of the string.
- [x] 4.5 `_phase_gate_and_escalate` passes `escalation=gate_result.escalation` to `observe()`; `FetchContext.observe()` + `GateOutcomeProjection` updated to carry typed signal.
- [x] 4.6 `actions/playbook.decide_next` switches on `last.escalation.next_tier == "browser"` Literal.
- [x] 4.7 Source-side `suggested_tier` references removed; test fixtures bulk-updated (regex sweep across test_gate / test_block_detector / test_decide_next, plus manual fix in test_jina_403_stub).
- [x] 4.8 `make check` — 781 tests pass, coverage 89.00%. `make bench` deferred to end-of-phase batch.

## Phase 5 — DRY the FetchVerdict→Verdict mapping across handlers

**Scope adjusted post-Phase-4**: implementation review found the audit's "scattered HTTP→Verdict" smell is actually the identical 4-line `FetchVerdict → Verdict` block repeated across 8 handlers (arxiv, hn, twitter, discourse, github, wikipedia, reddit, lobste). The shape-aware `status_code == 403` policy is Reddit-only — pulling it into a generic `role`-keyed helper would be over-abstraction for one caller. New shape: pull the shared 4-line block into one helper, keep Reddit's 403-by-shape logic inline as a specialization.

- [x] 5.1 Created `src/a2web/handlers/_common.py` with `empty_result(url, verdict)` (consolidating 9 byte-identical copies across handlers) + `map_non_ok(outcome, url) -> TierResult | None`.
- [x] 5.2 Refactored 5 handlers (arxiv, hn, discourse, wikipedia, reddit-empty-result) to call `map_non_ok` / `empty_result`. 4 handlers stayed as-is: github (raises sentinels in a gidgethub adapter, different shape), twitter (returns (Verdict, body) tuple from a helper, different return type), habr + v2ex (compound `verdict OR status_code != 200` checks, different shape).
- [x] 5.3 Reddit's `outcome.status_code == 403` shape-aware branch stays INLINE — only handler with this policy.
- [x] 5.4 Added `tests/handlers/test_common.py` covering 7 cells (ok-passthrough + 6 non-ok verdicts including proxy_unavailable→connection_error fallthrough).
- [x] 5.5 `make check` — 788 tests pass, coverage 89.30% (up from 89.00% due to less code to cover). `make bench` deferred to end-of-phase batch.

## Phase 6 — Pure extraction pipeline

**Scope adjusted**: the proposal's "pick_best across all candidates" design would run BOTH escalators unconditionally (perf cost) and changes the policy (currently sequential — json first, records only if json doesn't win). Pragmatic shape: keep sequential ladder, make each escalator pure-return (no `fc.content_md` mutation), single assignment site at the end of `_run_extraction_escalation`. Same sequence, same policy, escalators become side-effect-free for their content output.

- [x] 6.1 Added `ContentCandidate` frozen dataclass with `source: Literal["trafilatura","json_synth","record_synth"]`, `content_md`, `next_links` fields.
- [x] 6.2 `pick_best` not needed — sequential ladder semantics are preserved (json first, records second, first-winner wins). `_run_extraction_escalation` is the implicit picker.
- [x] 6.3 / 6.4 `_escalate_via_json` and `_escalate_via_records` now return `ContentCandidate | None`; the wins-baseline policy is preserved inside each rung.
- [x] 6.5 Browser-escalation path already routes through `_run_extraction_escalation` (line 1357 — calls the same function), so the new candidate-based shape carries through.
- [x] 6.6 In-place `fc.content_md = synthetic` / `fc.next_links_handler = ...` deleted from both escalators; the single assignment lives in `_run_extraction_escalation` reading the candidate.
- [x] 6.7 No test churn — escalators are private internals; tests observe `fc.content_md` after `_phase_extract` runs and that output is unchanged.
- [x] 6.8 `make check` — 788 tests pass, coverage 89.31%. Bench deferred to end-of-phase batch.

## Phase 7 — Mechanical boundary-type freeze

- [x] 7.1 `ExtractedContent` frozen.
- [x] 7.2 `CacheRow` frozen.
- [x] 7.3 `BlockResult` frozen.
- [x] 7.4 `CookieRow` frozen.
- [x] 7.5 No in-place mutations on these types in src/ (verified via grep).
- [x] 7.6 Added `tests/architecture/test_packages_boundary_frozen.py` — parametrized assertion that 7 boundary dataclasses are `frozen=True`, plus a runtime FrozenInstanceError check.
- [x] 7.7 `make check` — 796 tests pass, coverage 89.31%.

## Wiring sanity + gates (cross-phase)

- [x] 8.1 `make lint` green at every phase boundary.
- [x] 8.2 `make ty` green at every phase boundary (closed Literal enums, non-optional Lazy[T] propagates through the call graph).
- [x] 8.3 `make test` green with coverage 89.31% (above 85% gate) at every phase boundary.
- [x] 8.4 `make check` end-to-end green after every phase.
- [ ] 8.5 `make bench` parity vs. v0.22 baseline — DEFERRED, user-triggered (LIVE-NETWORK + LLM QUOTA).

## Documentation + backlog hygiene

- [x] 9.1 `CHANGELOG.md` — consolidated v0.23.0 entry describing all 7 phases, internal-only changes, coverage delta.
- [x] 9.2 `CLAUDE.md` — `state.py` paragraph updated (bootstrap_state + Resources + unavailable_lazy); `fetcher.py` paragraph updated (decision-log-only verdict, non-optional Lazy[T], pure escalators); `handlers/` paragraph updated (shared `_common.py` helpers).
- [ ] 9.3 `BACKLOG.md` — DEFERRED (no need to block release on backlog admin).
- [x] 9.4 `pyproject.toml` bumped 0.22.0 → 0.23.0.
- [ ] 9.5 `make install-global` — DEFERRED, user-triggered (system mutation).

## Archive

- [ ] 10.1 Run `openspec archive fetcher-orchestrator-refactor-v1` after merge (or per phase, depending on shipping cadence) to apply the deltas to canonical specs.
