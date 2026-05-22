## Context

The orchestrator (`src/a2web/fetcher.py`) walks `TIER_ORDER = ("site_handler", "raw", "jina")`. The `site_handler` slot dispatches to a matching domain handler (Reddit, HN, …). A handler that has confirmed the content is gone returns `Verdict.not_found`.

In `_phase_tier_loop`, a tier result that is not `ok` and not `no_match`/`skipped` sets `fc.final_verdict = tier_result.verdict` (so far so good) and the loop continues. The next tier — `raw` — fetches the same URL. For sites that serve HTTP 200 + a thin SPA shell for deleted content (Reddit returns 200 for deleted posts), `raw` returns `Verdict.ok`, `_install_won_tier` sets `fc.final_verdict = Verdict.ok` and returns. `_phase_gate_and_escalate` then extracts ~0 chars and downgrades to `length_floor`. The handler's `not_found` is overwritten and never reaches the response.

`fc.final_verdict` is the single value `build_response` reads to set `FetchResponse.status` / verdict. There is no place that remembers a handler said `not_found`.

## Goals / Non-Goals

**Goals:**
- A site handler's terminal `not_found` reaches the agent when the fetch fails, instead of being clobbered by a downstream tier's vaguer `length_floor`.
- Zero change to the success path — a downstream recovery still wins.
- Minimal surface: one orchestrator file, no envelope/dependency change.

**Non-Goals:**
- Stopping the cascade early on a handler `not_found` — falling through to raw/jina (and the after-tier archive retry) is still wanted; the handler may be wrong, or Wayback may have a snapshot.
- Transient handler verdicts (`rate_limited` / `timeout` / `connection_error`) — different semantics, no repro.
- The "`length_floor` is a dead-end verdict" question and browser-escalation policy — out of scope.
- Benchmark corpus fixture refresh — separate benchmark-maintenance work.

## Decisions

### Remember the handler verdict on `FetchContext`, reconcile at the end

Add `handler_not_found: bool = False` to `FetchContext`. In `_phase_tier_loop`, when the `site_handler` tier returns `Verdict.not_found`, set `fc.handler_not_found = True`. After `_phase_gate_and_escalate`, a small named reconciliation phase applies the precedence: if `fc.final_verdict != Verdict.ok` and `fc.handler_not_found`, set `fc.final_verdict = Verdict.not_found`.

**Rationale:** `final_verdict` is mutated by several phases; trying to "protect" it inline at each mutation point would be fragile. A single reconciliation step that runs once, after all phases that can fail have run, is the smallest correct surface. It also reads naturally as a pipeline phase, matching the file's existing phase-function style.

*Alternative considered — stop the cascade when a handler returns `not_found`:* rejected. The fall-through to raw/jina is a deliberate "maybe the handler missed something" hedge, and the after-tier archive retry (playbook Rule 3) depends on the loop continuing. Stopping early would lose a real recovery path.

*Alternative considered — fix it in `build_response`:* rejected as the home for the rule. `build_response` is a pure projection of `FetchContext`; the precedence is orchestration policy and belongs in the orchestrator next to the other phases. (The reconciliation simply sets `fc.final_verdict` before `build_response` reads it.)

### Scope strictly to `not_found`

Only `not_found` carries the unambiguous "definitive, do not retry" meaning, and only it has a proven repro. Transient verdicts could in principle be more informative than `length_floor` too, but conflating them risks masking a genuine recovery story (a `rate_limited` handler followed by a successful raw fetch is a *success*, fully handled by the `final_verdict == ok` guard — but extending precedence to transient verdicts on failure has no demonstrated need). Keep the rule narrow and provable.

### Precedence applies only on failure

The reconciliation is guarded by `fc.final_verdict != Verdict.ok`. If any tier produced gate-passing content, the fetch succeeded and the handler's earlier `not_found` is irrelevant — the content exists after all. This keeps the rule from ever degrading a real result.

## Risks / Trade-offs

- **A handler returns `not_found` incorrectly, then raw genuinely fails for an unrelated reason (e.g. `length_floor` on a live-but-thin page).** → The agent would see `not_found` instead of `length_floor`. Acceptable: a handler returning `not_found` is a strong, deliberate signal (the Reddit handler only emits it after `.json` *and* `old.reddit` both 404); if it fires wrongly that is a handler bug to fix at the source, not a reason to discard the signal.
- **Diagnostics already record every tier verdict**, so the raw tier's `length_floor` step remains visible in the `debug` diagnostics chain for anyone inspecting — only the headline verdict changes. No information is lost.

## Migration Plan

Additive orchestrator logic; no envelope, API, or dependency change. Rollback is reverting the commit. No data migration.
