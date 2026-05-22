## Context

The fetch orchestrator (`src/a2web/fetcher.py`) carries one fetch's state in a single mutable `FetchContext`. `final_verdict: Verdict` is a scalar slot written by at least five sites — the tier loop (`_phase_tier_loop`), the gate (`_phase_gate_and_escalate`), `_regate_after_escalation`, and the bespoke `_phase_reconcile_verdict`. Last write wins. Every recurring defect is the same mechanical failure: an authoritative verdict (a site handler's `not_found`, a soft-block) is clobbered by a later, vaguer write.

This has surfaced three times in two days: the `handler-verdict-precedence` change (a reconciliation phase + a `handler_not_found` side-channel flag — itself proof of the structural defect, since it repairs exactly one known collision); the deleted-post benchmark over-diagnosis; and the Reddit listing soft-block, where the handler *knows* later tiers will also fail but has no signal to say so (`no_match` is overloaded and falls through anyway).

A four-prong research effort — scrape-framework prior art, software-design-pattern theory, resilience/distributed-systems papers, and correctness-by-construction — independently converged on one structure: an **append-only observation log** with **pure total projections**. See "Research basis" below.

**Constraints:** `dataclass(slots=True)` for internal pipeline objects, pydantic only at boundaries (CLAUDE.md). No wire/envelope change permitted without explicit sign-off — this change keeps `FetchResponse` output byte-identical. `ty` (Astral) is the type checker; `make check` gate at ≥85% coverage.

## Goals / Non-Goals

**Goals:**
- Make the verdict-clobber bug *class* unrepresentable — not patched. No mutable verdict slot can exist to overwrite.
- Verdict precedence becomes one pure, total, exhaustively-tested function — retiring `handler_not_found` + `_phase_reconcile_verdict`.
- Escalation policy lives in exactly one pure planner fed the whole fetch history; the orchestrator holds zero inline policy.
- Fix the Reddit soft-block at its source: handlers get cookies; `no_match` stops being overloaded.
- Ship in two independently-valuable phases; Phase 1 alone kills the bug class.

**Non-Goals:**
- No wire/envelope/MCP-API change. `FetchResponse` output is identical for identical inputs.
- The resilience layer (cross-tier retry budget, p95-gated hedging, learned tier ordering) — real, researched, but a separate future change.
- No dynamic tier ordering / state-machine rewrite. `TIER_ORDER` stays a fixed tuple; the defect was never the order, only the stop condition and the lost signals.
- No full Event Sourcing infrastructure (event store, snapshots, replay) — only the in-process projection subset.

## Decisions

### D1 — An append-only `Observation` log replaces the mutable verdict slot

One fetch produces an immutable, append-only sequence of typed `Observation`s. Every tier attempt, gate evaluation, and escalation appends one; nothing is ever overwritten. An `Observation` is a frozen dataclass carrying at least: `verdict: Verdict`, `source` (which tier/handler/gate produced it), `authoritative: bool` (the source vouches this verdict is definitive for its domain), `t_ms`, and structured evidence.

**Rationale.** Every bug is last-write-wins on a scalar. If the verdict is *never stored*, only *appended*, an earlier authoritative signal is physically still present — it can only be out-prioritised by an explicit, testable rule, never lost. This is the Decider pattern's `evolve` half (Chassaing) and the projection-only subset of Event Sourcing.

*Alternative — keep the mutable slot, add more reconciliation phases:* rejected. That is the patch treadmill `_phase_reconcile_verdict` already started; each new authoritative signal needs its own bespoke rescue.

*Alternative — full Event Sourcing:* rejected as overkill. Event stores, versioning, snapshots, and replay solve cross-process durability problems a single in-process fetch does not have. Adopt only the append-log + projection.

*Alternative — Railway-Oriented Programming:* rejected as the wrong shape. ROP models a linear success/failure pipeline; this cascade branches out-of-order (`RewriteUrl` restarts the loop, archive/browser fire sideways, a later tier *recovers* what an earlier one failed). ROP has no vocabulary for "track A produced an authoritative value, track B later produced a vague one — keep A."

### D2 — `resolve_verdict(log) -> Verdict`: a pure, total projection

The final verdict is *derived* on demand, never stored. `resolve_verdict` is a pure function with an explicit precedence:

1. If any observation is a successful gate-passing result → `ok` (a genuine downstream recovery always wins).
2. Otherwise, among failure observations, the highest-precedence verdict wins. Precedence is a function of `(authoritative, verdict)`: an authoritative observation outranks a non-authoritative one; within each tier, a fixed verdict ranking (definitive verdicts — `not_found`, `paywall`, `anti_bot` — outrank vague ones — `length_floor`, `other`). The exact total ordering is pinned in the `cascade-decision-log` spec.
3. The empty log is a defined case, not an edge case → an explicit verdict.

It is made **total** by exhaustive `match` over `Verdict` closed with `assert_never`; adding a `Verdict` member breaks the build until handled. Match one enum at a time — tuple-of-enum exhaustiveness is unreliable in current Python type checkers.

**Rationale.** "Derive, don't store" — a recomputed read model cannot drift; there is no second copy to fall out of sync. The `handler-verdict-precedence` rule collapses from a phase into one precedence row applied uniformly to *every* authoritative signal.

### D3 — `decide_next(log, caps) -> Action`: the playbook becomes a pure planner

`actions/playbook.py` already aspires to be the policy module but is starved — `next_action_after_tier` sees only `(tier_result, url)`. It becomes `decide_next(log, caps) -> Action`, fed the whole history. The `Action` set grows: today's `RewriteUrl` / `RetryViaArchive` / `Skip` plus `EscalateBrowser` and a stop-live-tiers action. `decide_next` is structured as a decision table over `(resolved verdict × tier-exhausted × browser-budget × archive-eligible)` and unit-tested for completeness — every condition combination maps to exactly one `Action`.

The orchestrator becomes a pure **executor** (Functional Core / Imperative Shell): do tier I/O, append observations, run the returned `Action`. It holds no policy. The gate's inline `suggested_tier == "browser"` decision moves into `decide_next` — which means a *total* failure (no tier won, gate never ran) can finally route to the browser, the case today's architecture cannot reach.

### D4 — Split `no_match`; give handlers cookies

`no_match` is restricted to its one true meaning: "no handler claims this URL." A handler that *claims* a URL but fails — Reddit soft-block, empty listing — MUST return a real verdict observation (`rate_limited` for a `{"error": 429}` 200-body; `not_found` for a genuinely empty listing). The `SiteHandlerTier` dispatch seam threads the resolved cookie jar (`fc.cookies` / `fc.cookies_full`) into `Handler.fetch`; the Reddit handler uses it on its `httpx` client. An authenticated `.json` request barely throttles — this fixes the original soft-block symptom at its source rather than escalating around it.

### D5 — Property-based tests for the projections

`resolve_verdict` and `decide_next` are pure and total, so they are exhaustively testable offline (no network). Generate arbitrary `list[Observation]` and assert invariants: **order-independence** (`resolve(log) == resolve(shuffle(log))` — the property that makes the overwrite bug impossible to reintroduce), precedence-respecting, append-only monotonicity, idempotence, totality/never-invalid. Hypothesis is the natural tool; whether to add it as a dev-only dependency is an open question (D5 fallback: exhaustive parametrized tests over the closed `Verdict` enum).

### D6 — The decision log is a sibling of LDD events, not the same object

a2web already emits typed LDD events (`TierEnded`, `StageEnded`). Tempting to reuse them as the log — but LDD events are tuned for *observability* (verbosity, sinks, OTel) and their schema should be free to change without breaking control-flow correctness. The `Observation` log is a separate typed structure; it may share enum/value types with LDD events but is versioned independently. Observations can be *emitted as* LDD events for visibility, but control flow reads the log.

### Phasing

- **Phase 1 — lossless verdict.** `Observation` + append-only log; `resolve_verdict`; tiers/gate/escalators append; `final_verdict` becomes a derived property; retire `handler_not_found` + `_phase_reconcile_verdict`; property tests. Kills the bug class. Ships independently — internal-only, no wire change.
- **Phase 2 — unified planner.** `decide_next` over the log; orchestrator → pure executor; gate's browser routing folded in; `no_match` split; handler cookie plumbing; `build_response` as a projection.

## Risks / Trade-offs

- **Large blast radius in `fetcher.py`.** → Phase the work; Phase 1 is independently shippable and self-contained. Each phase passes `make check` before the next starts.
- **Silent behavior drift — `FetchResponse` output must stay byte-identical.** → The existing contract tests (`tests/contracts/`) and capability tests are the guard; run them as a characterization baseline before and after each phase. Any diff is either a bug or a deliberate, called-out improvement.
- **Type-checker exhaustiveness gaps.** `match` over a tuple of enums is unreliable in mypy/`ty`. → Match one enum at a time; close every dispatch with `assert_never`.
- **Re-deriving projections instead of caching a field.** → Negligible: an in-process fold over dozens of observations per fetch. Correctness over a micro-optimisation.
- **`handler-verdict-precedence` was shipped 6 days... days ago and is now superseded.** → Clean supersede: its spec requirement is REMOVED in the `tier-pipeline` delta, its behavior fully absorbed by `resolve_verdict`, and its tests are rewritten as `resolve_verdict` precedence tests. No capability is lost.

## Migration Plan

Internal refactor — no data migration, no wire change, no consumer-visible API change. Phase 1 and Phase 2 each land as their own commit(s) on `main`, each gated by `make check`. Rollback is reverting the commit(s). The `handler-verdict-precedence` archived change stays archived; this change's `tier-pipeline` delta records the supersede.

## Open Questions

1. **Stop-live-tiers vs. archive.** A handler `not_found` deliberately keeps the loop alive today so Wayback can be tried (playbook Rule 3). The new stop action therefore cannot be a hard stop — it must mean "stop trying *live* tiers; archive escalation still permitted." Confirm this is the exact semantics, and name the action accordingly (e.g. `StopLiveTiers`).
2. **Hypothesis as a dev dependency.** Property-based testing is the strongest guard for `resolve_verdict`/`decide_next`. Adding Hypothesis needs sign-off (CLAUDE.md "Ask First: new dependencies"). Fallback: exhaustive parametrized tests over the closed `Verdict` enum.
3. **Does the `Observation` log subsume `FetchContext.diagnostics`?** The existing `Diagnostic` list and the new log overlap heavily. Folding `diagnostics` into a projection of the log would remove a parallel structure — but it touches the debug-envelope path. Decide whether Phase 2 unifies them or leaves `diagnostics` as a separate projection.
4. **Exact precedence ordering** for all twelve `Verdict` values — pinned in the `cascade-decision-log` spec; needs a final pass against real fetch traces.

## Research basis

Four parallel research prongs (2026-05-22), all converging on append-only log + pure projection:

- **Prior art** — trafilatura emits immutable extraction candidates and a separate scorer picks the winner (nothing mutated); Crawlee models a soft-block as a first-class signal on a separate channel (`Session.mark_bad/retire`). No surveyed framework combines a typed observation log that is *simultaneously* the verdict source, the planner input, and the response projection.
- **Design theory** — the Decider pattern (Jérémie Chassaing, "Functional Event Sourcing Decider"); Functional Core / Imperative Shell (Gary Bernhardt, "Boundaries"); "make illegal states unrepresentable" (Wlaschin lineage). Railway-Oriented Programming explicitly rejected — wrong shape for out-of-order branching.
- **Resilience** — Nygard, *Release It!* (fallback ≠ recovery); Dean & Barroso, "The Tail at Scale" (CACM 2013 — hedge within a tier when sources are equivalent, fall back across tiers when not). Informs the out-of-scope Phase 3.
- **Correctness-by-construction** — Amey & Chapman (CbyC manifesto); totality via exhaustive `match` + `assert_never`; property-based testing of pure decision functions (order-independence, precedence, monotonicity, idempotence); "derive don't store" — a projected read model cannot drift.
