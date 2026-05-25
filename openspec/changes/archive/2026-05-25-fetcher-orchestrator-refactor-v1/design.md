## Context

`src/a2web/fetcher.py` is 1514 LOC of orchestrator code. `FetchContext` is a 40+ field dataclass that pretends to be "decision log + helpers" but actually carries mutable snapshots that drift from the log projection. Three construction paths for `AppState` exist independently (production, eval, tests), and that drift was the root cause of the 2026-05-25 bench bug where `BrowserPool` wasn't wired through the eval harness.

Two of the most recent shipped changes (`refactor-ask-to-router-shape` v0.21, `expand-js-shell-markers` v0.22) each touched the boundary/projection layer and the escalation signal path. Both revealed friction: the gate's `suggested_tier="browser"` string is the only escalation signal that flows up to the planner, but the new JS-challenge marker fix can't add a different escalation type without re-stringing the contract. The router-shape change needed a new `_project_routing` seam — but `_project_*` is a pattern that only exists for the LLM payload; equivalent boundary types in `content_extract` and `block_detector` use inline projection inside domain helpers.

A 4-axis parallel-agent audit (`Researches/132-a2kit-structural-audit` pattern) cross-confirmed seven structural smells. Three Tier-1 smells were flagged by multiple agents and are blocking smooth iteration:

1. **Dual-semantics state slots** — `gate_verdict` snapshot vs. `resolved_verdict()` projection; `Lazy[T] | None` conflates two unrelated optionality categories.
2. **Three construction paths drift** — production / eval / tests reinvent the wheel; v0.22 bench gap proved this is a live failure mode.
3. **Escalation contract scattered across gate / planner / orchestrator / handler** — adding a new escalation type touches four layers.

The proposal stages a single refactor across 7 phases so each ships at a green-gate checkpoint. The themes are intertwined (you can't typed-EscalationSignal without unified state to carry it), so they belong in one change — but the phases are sequenced so each is independently mergeable.

## Goals / Non-Goals

**Goals:**
- One source of truth for state — `bootstrap_state(...)` factory used by all three paths (production / eval / tests).
- One source of truth for verdict — pure projection of the decision log; no parallel `gate_verdict` snapshot.
- One source of truth for escalation signals — typed `EscalationSignal` value carried on observations; planner reads typed evidence; orchestrator dispatches.
- Pure extraction-pipeline contract — phases return candidates; pick-best is pure; no in-place `fc.content_md` mutation.
- Lazy[T] type discipline — non-optional at the seam; stub-on-unavailable for direct-call paths.
- Boundary-type consistency — all package boundary dataclasses frozen.

**Non-Goals:**
- Public tool API or wire-envelope changes (NONE — `ask` / `fetch_raw` are unaffected).
- Resource-protocol unification (Sqlite-crash vs. Llm-degrades) — significant scope, deferred to follow-up.
- URL-shape router DRY-out for handlers — DX win, deferred.
- Package folder/flat convention enforcement — DX win, deferred.
- Render parity tests across handlers — testing investment, deferred.
- Handler failure visibility in the response envelope — operator UX, deferred.

## Decisions

### D1 — Single proposal with phased ship, not seven small proposals

The themes are intertwined: typed `EscalationSignal` (Phase 4) needs the decision-log to carry typed payloads, which requires the `gate_verdict` snapshot removal (Phase 2). The pure extraction pipeline (Phase 6) needs the new state seam to thread candidates without mutating `fc`. Splitting into seven separate openspec changes would mean each one carries a "this depends on changes X, Y, Z" preamble and we'd lose the "single coherent reshape" framing.

But within the proposal, each PHASE is a green-gate checkpoint — `make check` + bench parity between phases. Reviewing the change in seven git commits is the natural cadence; reverting at a phase boundary is safe.

### D2 — Keep `FetchContext` as a dataclass (don't introduce a new container shape)

Tempting to replace `FetchContext` with a builder, a state machine, or a layered struct. Rejected: the current dataclass-of-named-fields IS a good shape; the problem is which fields it has, not the shape itself. Removing slots that duplicate the log is the fix.

### D3 — `bootstrap_state` returns `(AppState, Resources)` tuple, not a merged container

Production `app.provide(...)` registrations are individual — each resource registers separately so a2kit can wire lazy lifecycle. The factory exposes the pieces; production assembles via `provide`, eval / tests assemble directly. Don't introduce a "MegaContainer" that hides the individual provider pattern.

### D4 — `EscalationSignal` is a frozen dataclass, not a Literal

```python
@dataclass(frozen=True, slots=True)
class EscalationSignal:
    next_tier: NextTier  # Literal["browser", "tls_impersonate", "archive"]
    reason: str          # human-readable; ≤80 chars
```

Considered: just promote `NextTier` to a Literal and inline. Rejected: the `reason` field IS valuable for diagnostics (the gate's `subsystem` already carries this information; making it part of the signal contract preserves it explicitly). Frozen dataclass + Literal field gives both type-safety on `next_tier` AND the diagnostic string.

### D5 — `pick_best` is a free function with explicit policy, not a method on a class

```python
def pick_best(candidates: list[ContentCandidate]) -> ContentCandidate | None:
    """Length-aware for flat; threading-aware for record-sets. Returns
    None when no candidate beats the floor."""
```

Considered: a `BestCandidatePolicy` protocol with implementations. Rejected: there's exactly one policy, and the existing length+threading rule lives in `_escalate_via_records` already — extract as a free function, not a class hierarchy. If a future case needs different policy, escalate to a protocol then.

### D6 — `http_to_verdict` helper takes a `role` enum, not handler-specific overrides

The role enum (`listing | thread | permalink | search | other`) is the discriminator that explains why Reddit currently maps 403 differently per shape. Lifting it to a parameter is the right factoring — the *policy* "403 on a listing means connection_error, 403 on a thread means try-archive" is shared across sites, not Reddit-specific. The shared helper makes the policy reviewable in one place.

### D7 — Phase ordering: state foundation before signal typing

The seven phases are ordered to minimize churn:
1. Bootstrap factory (no semantics change) — pure consolidation
2. Decision-log-only verdict (small semantic change; cleanups)
3. Lazy[T] non-optional (stubs allow the rest to assume invariants)
4. Typed EscalationSignal (needs Phase 2's clean log)
5. http_to_verdict shared helper (consumes Phase 4's signal type)
6. Pure extraction pipeline (uses Phase 1's resources cleanly)
7. Mechanical boundary freeze (independent; ship anywhere)

Phase 7 could ship first or last; placed last to keep the conceptual story together. A reviewer can reorder if helpful.

### D8 — Bench parity check between phases

Each phase's gate includes "run `make bench` and confirm reach + cost are unchanged vs. v0.22 baseline." This is the integration test for "we didn't break behavior." It's slow (~3 min + LLM quota) but it's the only test that exercises the full cascade against real sites. If a phase's bench diverges from baseline, that's a finding to investigate before merging the phase.

## Risks / Trade-offs

### Risk: Big-bang refactor blast radius

Seven phases touch most of `fetcher.py`, every `handlers/*`, `state.py`, `server.py`, `playbook.py`, eval harness, tests. Mitigation: phase staging with green-gate per phase; existing 89% test coverage + contract tests + bench parity each catch different regression classes; if any phase reveals an unaccounted-for coupling, pause and pivot the design.

### Risk: Test churn

Every phase will require test updates because tests directly read `FetchContext` slots. Mitigation: tests use `make_default_state` which is the seam — Phase 1 stabilizes that. Subsequent phases update tests as field names change; ~50-100 tests touched in total but each touch is mechanical.

### Risk: Bench cost across phases

7 phases × ~$1.40 per `make bench` run = ~$10 in LLM quota for full validation. Mitigation: only the phases that change behavior need a full bench (1, 2, 4, 5, 6); the pure consolidation / mechanical phases (3, 7) only need `make check`. So actual bench spend is ~$7.

### Trade-off: Phase 5 (`http_to_verdict` helper) standardizes Reddit's intentional per-shape mapping

Reddit currently maps 403 → `not_found` for threads (so archive escalation fires) but `not_found` is wrong for listings (no thread to archive). The standardized helper makes this policy explicit per `role`, but it changes the verdict-on-the-wire for some currently-broken cases (e.g. Reddit listing 403 would change from `connection_error` → ... what? The current code returns `connection_error` because there's nothing to retry. The new helper would return ... the same? Need to decide per-role what 403 means.)

This is a design question to settle during Phase 5 implementation: write the policy table first, review it, then refactor handlers. If the policy table reveals true ambiguity (a real "what should 403 mean here?" question), surface it back to design.md as an addendum before shipping Phase 5.

### Risk: Phase 6 (extraction pipeline) is the highest-effort phase

The current `_phase_extract` + `_run_extraction_escalation` + `_escalate_via_json` + `_escalate_via_records` flow has 200+ LOC of in-place mutation patterns. Lifting to candidate-list-returning purity will require careful unwinding. Mitigation: write the `ContentCandidate` + `pick_best` types first; convert each escalation step to produce a candidate instead of mutating; flip the call site last. Existing tests exercise the escalation paths thoroughly.

### Risk: Production lifecycle subtleties (Phase 3 stubs)

The stub-on-unavailable pattern needs to actually raise something callers can handle. The current `_escalate_browser` checks `if fc.browser_pool is not None`; with non-optional Lazy, the stub raises `ResourceUnavailable` inside the await, and the caller needs to catch and emit an operator hint. Mitigation: model the stub after `LlmExtractorResource.unavailable_reason` (already proven); the existing operator-hint path is the catch.

## Probes / Reference Material

- Audit findings: this proposal's parent exploration thread (2026-05-25 4-agent parallel audit).
- Pattern reference: `Researches/132-a2kit-structural-audit` — same parallel-agent methodology applied to a2kit; produced 3 OpenSpec proposals.
- Bench parity baseline: `eval/findings_2026-05-25-router-shape-prod-bench.md` (v0.21 baseline; v0.22 bench has the browser-pool fix).
- The just-discovered 2026-05-25 browser_pool drift bug: lives in `llm_eval/systems.py` and `__main__.py`; fixed in the v0.22 release. This was the canonical example of "three construction paths drift" — Phase 1 prevents the next drift bug structurally.
- v0.21 / v0.22 design.md files in `openspec/changes/archive/2026-05-25-*` — context for why the current shape exists and what the recent friction looked like.
