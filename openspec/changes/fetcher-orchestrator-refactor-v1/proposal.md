## Why

A 2026-05-25 parallel-agent audit (4 read-only agents on distinct axes; cross-confirmed findings) surfaced two clusters of architectural coupling that are now load-bearing on most upcoming work:

**Theme A — multiple sources of truth for state.** `FetchContext` slots like `gate_verdict` (mutable snapshot) live alongside `resolved_verdict()` (pure projection of the decision log) — they can diverge after re-gate. `Lazy[T] | None` conflates "resource not provisioned" with "resource not yet invoked" — three resource phases each invent their own None-check. Three construction paths exist for `AppState` (production `app.provide(...)`, eval harness manual construction, test `make_default_state`) — drift between them is exactly what caused the v0.22 bench to silently undercount browser-tier wins (eval harness wasn't wiring `BrowserPool`; fixed 2026-05-25 in-flight).

**Theme B — escalation contract scattered across four layers.** Block detector sets `suggested_tier="browser"` as a string field; planner reads the string + caps; orchestrator executes + increments cap counters; handlers map HTTP 4xx → `Verdict` with per-handler inconsistencies (Reddit maps 403 → `not_found` for threads but `connection_error` for listings — same handler!). Content-extraction escalation mutates `fc.content_md` in place across phases, with phase order silently load-bearing. Boundary→pydantic projections follow one pattern in `_project_routing` and a different one (inline mutation) in `extract_markdown` / `evaluate`.

Both clusters are symptoms of the same shape: **decisions / state that should be immutable values flow through mutable slots, and the layers that produce them communicate through stringly-typed fields rather than typed payloads.** This proposal addresses both with a single refactor staged across 7 phases, each ending at a green-gate checkpoint.

While we're touching the boundary layer, also fold in a mechanical sweep to freeze the four un-frozen boundary types (`ExtractedContent`, `CacheRow`, `BlockResult`, `CookieRow`) so the boundary-as-seal pattern is consistent.

OUT OF SCOPE: resource-protocol unification (Sqlite-crashes-vs-Llm-degrades), URL-shape router DRY-out, package folder/flat convention, render parity tests, handler-failure visibility in response envelope. All deferred to BACKLOG with explicit reasons.

## What Changes

### Phase 1 — Unify state construction (Theme A core)
- **New**: `src/a2web/state.py::bootstrap_state(settings)` async factory that returns `AppState` + a `Resources` bundle (`BrowserPool`, `LlmExtractorResource`, `CookieJarResource`). Production `app.provide` registrations, eval harness, and tests all call this single factory.
- **Refactor**: `server.py` provider registrations delegate to `bootstrap_state` parts; `llm_eval/__main__.py` calls `bootstrap_state` directly; `tests/conftest.py::make_default_state` becomes a thin wrapper.
- **Outcome**: a new resource added in one place automatically reaches all three paths. Drift impossible by construction.

### Phase 2 — Decision-log-only verdict (Theme A)
- **Remove**: `FetchContext.gate_verdict`, `FetchContext.gate_subsystem` (mutable snapshots).
- **Replace**: all reads with `fc.resolved_verdict()` or a new `fc.last_gate_outcome()` projection.
- **Outcome**: one source of truth; re-gate cannot create snapshot/projection divergence.

### Phase 3 — Lazy[T] non-optionality (Theme A)
- **Change**: `Lazy[BrowserPool] | None` → `Lazy[BrowserPool]` (non-optional) throughout `FetchContext` + `fetcher.fetch(...)`.
- **New**: stub thunks in `state.py` for direct-call paths that raise `ResourceUnavailable` on invocation (with operator hint, not crash).
- **Outcome**: phases stop checking `if fc.browser_pool is not None`; the type system enforces the seam.

### Phase 4 — Typed `EscalationSignal` (Theme B core)
- **New**: `src/a2web/actions/signal.py` — `EscalationSignal(next_tier: NextTier, reason: str)` frozen dataclass where `NextTier = Literal["browser", "tls_impersonate", "archive", None]`.
- **Replace**: `BlockResult.suggested_tier: str | None` → `EscalationSignal | None`; planner reads structured signal instead of string compare.
- **Replace**: `_OBSERVATION.suggested_tier` follows.
- **Outcome**: adding a new escalation = add a Literal value + planner case; no stringly-typed misspellings; gate's signal is typed evidence on the observation log.

### Phase 5 — Standardize HTTP→Verdict mapping in handlers (Theme B)
- **New**: `src/a2web/handlers/_verdict.py::http_to_verdict(status_code, *, role: Literal["listing","thread","permalink","search","other"]) -> tuple[Verdict, EscalationSignal | None]` shared helper.
- **Refactor**: Reddit / GitHub / V2EX / Habr / others all call the helper. Removes per-handler `if 403:` branches with inconsistent semantics.
- **Outcome**: a 403 means the same thing across handlers. Adding a new handler doesn't risk a new mapping convention.

### Phase 6 — Pure extraction pipeline (Theme B + addresses #4 hidden-ordering)
- **Refactor**: `_phase_extract` returns a sequence of `ContentCandidate(source, content_md, headings, links, score)` rather than mutating `fc.content_md` in place.
- **New**: pure `pick_best(candidates) -> ContentCandidate` function (length-aware for flat, threaded-aware for record-sets, per existing rules).
- **Outcome**: extraction escalation ladder reads candidates from prior phase, not from `fc.content_md`. Re-running the ladder after browser escalation becomes a pure re-invocation, not a re-mutation.

### Phase 7 — Mechanical boundary-freeze sweep (Tier 2 quick win)
- **Change**: add `frozen=True` to `ExtractedContent`, `CacheRow`, `BlockResult`, `CookieRow`.
- **Refactor**: convert any in-place field mutations on these types to construct-fresh-then-replace.
- **Outcome**: boundary-as-seal pattern is consistent. Removes a latent class of bugs (callers holding refs seeing mutation).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tier-pipeline`: `FetchContext` slot set changes (remove `gate_verdict` / `gate_subsystem`; `Lazy[T]` fields lose `| None`); extraction phase returns candidates instead of mutating; bootstrap factory becomes the single state-construction seam.
- `cascade-decision-log`: planner consumes `EscalationSignal` payloads on observations rather than string `suggested_tier` fields.
- `quality-gate`: `BlockResult.suggested_tier: str | None` replaced by `EscalationSignal | None` (typed payload, same semantics).
- `site-handlers`: HTTP-status-to-Verdict mapping unified via shared helper; per-handler inconsistencies removed.

## Impact

- **Code**: ~1500 LOC touched across `fetcher.py`, `state.py`, `server.py`, all `handlers/`, `actions/playbook.py`, `packages/block_detector.py`, `llm_eval/__main__.py`, `tests/conftest.py`. Each phase ships at a green-gate checkpoint (`make check` + bench parity).
- **API surface**: NO public tool-signature changes (the `ask` / `fetch_raw` MCP envelope shape is unaffected). Internal API: `FetchContext` field removals are breaking for any direct consumers (only eval / tests). `bootstrap_state` replaces three construction call sites.
- **Wire format**: unchanged. No envelope rewrite.
- **Tests**: existing tests carry forward with field-name updates; new tests for the bootstrap factory, EscalationSignal projection, http_to_verdict helper, and pure pick_best function.
- **Bench**: should produce identical or better Reddit / SPA results (no behavioral change, only structural).
- **Risk**: medium. Large refactor blast radius mitigated by 7-phase staging and the existing test gate (89% coverage + contract tests + bench parity check between phases).
- **Backlog**: closes the audit's TIER-1 cross-confirmed smells (#1 dual-semantics, #2 construction drift, #3 escalation scatter) and TIER-2 #5 (boundary freeze). Opens follow-up items: `unify-resource-protocol` (Sqlite-crash vs. graceful), `url-shape-router-helper` (handler DX), `package-folder-vs-flat-convention` (DX), `handler-failure-visibility-in-response` (operator UX).
