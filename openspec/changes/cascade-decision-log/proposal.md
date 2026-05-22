## Why

The fetch cascade keeps reproducing one defect: a strategy's authoritative knowledge — a site handler's `not_found`, a soft-block that guarantees later tiers also fail — is silently overwritten by a later step's vaguer verdict. The cause is structural: `FetchContext.final_verdict` is a single mutable slot that every phase writes, so the last writer wins. The `handler-verdict-precedence` change (shipped 2026-05-22) patched one collision with a reconciliation phase; the next soft-block fix would add another patch on top. Research across four literatures — scrape-framework prior art, the Decider pattern, resilience papers, correctness-by-construction — converges on one structural fix that makes the whole bug class *unrepresentable* rather than patched.

## What Changes

- One fetch produces an **append-only, immutable `Observation` log** — every tier, the gate, and every escalator *appends* a typed observation; nothing is ever overwritten.
- The final verdict becomes a **pure total projection** `resolve_verdict(log) -> Verdict` with an explicit, exhaustively-tested precedence order — replacing the mutable `final_verdict` slot.
- Escalation policy becomes a **pure planner** `decide_next(log, caps) -> Action` — the `actions/playbook.py` module, finally fed the whole fetch history (it sees only `(tier_result, url)` today). The `Action` vocabulary gains `EscalateBrowser` and a stop-live-tiers action.
- The orchestrator becomes a **pure executor**: it does tier I/O, appends observations, and runs the `Action` the planner returns — it holds **zero inline policy**. The gate's inline `suggested_tier == "browser"` decision moves into the planner.
- **BREAKING (internal only):** `FetchContext.final_verdict` and `FetchContext.handler_not_found` are removed and `_phase_reconcile_verdict` is deleted. The `handler-verdict-precedence` requirement is **superseded** — its one special case becomes one ordinary precedence row in `resolve_verdict`, applied uniformly to every authoritative signal. No wire/envelope/API change.
- The overloaded `no_match` signal is **split**: `no_match` means strictly "no handler claims this URL." A handler that claims a URL but fails (Reddit soft-block, empty listing) MUST return a real verdict observation, never `no_match`.
- Site handlers receive the resolved cookie jar at the dispatch seam — an authenticated Reddit `.json` request barely throttles, fixing the original soft-block symptom at its source.
- `FetchResponse` is built as a **pure projection of the log**; its output shape is unchanged.

Out of scope, noted for a future change: the resilience layer — cross-tier retry budget, p95-gated hedging, learned tier ordering.

## Capabilities

### New Capabilities
- `cascade-decision-log`: the append-only `Observation` log as the single source of truth for one fetch; the pure total projections `resolve_verdict` / `decide_next` / the response projection; the verdict-precedence contract; the planner `Action` vocabulary; the property invariants (order-independence, precedence, monotonicity, totality) that the projections must satisfy.

### Modified Capabilities
- `tier-pipeline`: the orchestrator becomes a pure executor of planner `Action`s — the tier loop appends observations instead of mutating `final_verdict`; browser and archive escalation route through `decide_next`. The `handler-verdict-precedence` requirement (handler `not_found` precedence) is superseded by `resolve_verdict`'s uniform precedence rule.
- `quality-gate`: the gate stops carrying escalation policy — it emits a verdict observation and no longer owns `suggested_tier` routing; the browser-escalation decision moves to the planner.
- `site-handlers`: `no_match` is restricted to "no handler claims this URL"; a matched-but-failed handler returns a real verdict observation. Handlers receive the resolved cookie jar through the dispatch seam.

## Impact

- `src/a2web/fetcher.py` — largest blast radius: `FetchContext` loses `final_verdict`/`handler_not_found`; the tier loop, `_phase_gate_and_escalate`, `_regate_after_escalation`, and `_phase_reconcile_verdict` are rewritten around the observation log; the orchestrator becomes a thin executor.
- `src/a2web/actions/playbook.py` — becomes the planner: `decide_next(log, caps) -> Action`, plus a richer `Action` set.
- `src/a2web/fetcher_response.py` — `build_response` becomes a pure projection of the log.
- `src/a2web/tiers/site_handler.py`, `src/a2web/handlers/` — `Handler.fetch` gains a cookies parameter; the Reddit handler stops abusing `no_match` and uses cookies.
- `src/a2web/models.py` — new `Observation` type(s); `Verdict` enum unchanged.
- Tests — `tests/capabilities/{tier_pipeline,quality_gate,site_handlers}/`; new property tests for `resolve_verdict` / `decide_next` (order-independence, precedence, monotonicity, totality). Property-based via Hypothesis if it is an acceptable dev-only dependency, otherwise exhaustive parametrized tests — resolved in design.
- No wire/envelope shape change — `FetchResponse` output is byte-identical for the same inputs; this is an internal restructure. No new top-level runtime dependency.
