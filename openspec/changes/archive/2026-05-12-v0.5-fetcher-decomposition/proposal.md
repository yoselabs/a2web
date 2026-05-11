# v0.5 — Fetcher decomposition

## Status

Draft. Stage 4 of the v0.5 punch list — the only remaining substantial
piece after Stage 1 (a2kit v0.27 migration) and the seven-package
migration. Deferred from autopilot because it restructures
orchestrator logic rather than moving files; a wrong move can subtly
break the gate ↔ escalation interplay.

## Context

`src/a2web/fetcher.py` is **895 LOC**. Function sizes by line range:

| Function | Lines | Purpose |
|---|---|---|
| `_phase_tier_loop` | 306–485 (**180 LOC**) | Walk TIER_ORDER, dispatch, handle 304/RewriteUrl/RetryViaArchive interruptions |
| `_phase_gate_and_escalate` | 536–612 (77 LOC) | Run gate; dispatch browser/archive on flag |
| `_phase_extract_answer` | 728–796 (70 LOC) | Domain-coupled LLM extract path |
| `_phase_cache_write` | 669–707 (39 LOC) | Cache-write gate |
| `_dispatch_archive` | 238–292 (55 LOC) | Out-of-band archive dispatch |
| `_escalate_browser` | 613–667 (55 LOC) | Out-of-band browser dispatch + regate |
| `_phase_extract` | 486–535 (50 LOC) | trafilatura + metadata + token counts |

The 180-LOC tier loop is the structural problem. It has three
interleaved responsibilities:

1. **Tier dispatch** — proxy acquire, fetch, emit events, report health
2. **Result classification** — silent skip / 304 reuse / verdict.ok install / failure
3. **After-tier action** — `RewriteUrl` (restart loop), `RetryViaArchive`
   (out-of-band escalation), or no-op

The control flow uses an outer `while True` + inner `for` + flag
variables (`restart_loop`, `archive_break_payload`) — a textbook sign
that the body wants to be split.

## Goals

1. Replace `_phase_tier_loop` with smaller named helpers — each
   responsible for one of the three concerns above.
2. Unify the shared boilerplate between `_dispatch_archive` and
   `_escalate_browser` (TierStarted/Ended emission + Diagnostic
   construction) without losing their real semantic differences.
3. Reduce `fetcher.py` total LOC. Target: under 700 LOC.
4. Zero behavioral change. The full test suite (320 tests) must pass
   with no edits.

## Non-goals

- **Do not** move `_phase_extract_answer` to `packages/llm_extract/`.
  It is intrinsically domain-coupled (FetchContext, FetchResponse,
  OperatorHint). Keeping it at the a2web seam is correct.
- **Do not** introduce new abstractions (Strategy classes, "PhaseRunner"
  framework). The phase functions are already a working composition.
  Decomposition means splitting a long function, not architecting.
- **Do not** change the public `fetch()` signature, response envelope,
  or LDD event shapes.

## Approach

### Phase A — extract `_run_tier_round` helper

A small helper that captures the "emit TierStarted, dispatch the
tier's fetch, emit TierEnded" boilerplate shared by the tier loop +
both escalation paths.

Signature sketch:

```python
async def _run_tier_round(
    tier: Tier,
    url: str,
    *,
    fc: FetchContext,
    state: AppState,
    ctx: a2kit.ToolContext,
    step_name: str,
    engine_static: str | None,
    proxy_url: str | None = None,
    conditional_extras: dict[str, str] | None = None,
) -> tuple[TierResult, int, int]:
    """Return (result, start_ms_relative, duration_ms)."""
```

Cuts ~25 LOC of duplication.

### Phase B — split `_phase_tier_loop` into named helpers

Three helpers, each ≤ 40 LOC:

- `_acquire_or_skip(fc, tier_name, proxy_pool)` → `ProxyHandle | None`,
  writes the `proxy_unavailable` Diagnostic on None. Returns the
  handle or `None` (caller `continue`s on None).
- `_handle_tier_result(fc, tier_result, tier_name, handle, tier_start_ms,
  tier_dur_ms)` → bool (`won`). Owns the 304-reuse path, the verdict.ok
  install, and the Diagnostic append. Returns True when the tier won.
- `_apply_after_tier(fc, tier_result, state, ctx)` → enum
  (`{REWRITE, ARCHIVE_INSTALLED, NONE}`). Owns the `RewriteUrl` and
  `RetryViaArchive` branches. Returns an enum the outer loop dispatches
  on.

The outer `_phase_tier_loop` becomes a ~30-LOC coordinator:

```python
async def _phase_tier_loop(fc, *, state, ctx):
    while True:
        action = None
        for tier_name in TIER_ORDER:
            handle = _acquire_or_skip(fc, tier_name, state.proxy_pool)
            if handle is None:
                continue
            result, t0, dt = await _run_tier_round(...)
            if result.no_match or result.skipped:
                continue
            state.proxy_pool.report(handle, success=...)
            won = _handle_tier_result(fc, result, tier_name, handle, t0, dt)
            action = await _apply_after_tier(fc, result, state, ctx)
            if action is _AfterTier.REWRITE:
                break  # restart while
            if action is _AfterTier.ARCHIVE_INSTALLED:
                return
            if won:
                return
        if action is not _AfterTier.REWRITE:
            return
```

### Phase C — merge `_dispatch_archive` + `_escalate_browser` (partial)

The two functions share boilerplate (emit + diagnostic build) but
diverge meaningfully:

| Aspect | archive | browser |
|---|---|---|
| Output | `_ArchiveOutcome`; caller installs | mutates `fc` in place |
| Diagnostic on failure | omitted (tried, didn't help) | always appended |
| Re-gate after install | caller does it | inline |
| Counter | caller increments | function increments |

A full merge would push these differences into conditional branches —
net cost ≥ benefit. Instead, factor the shared boilerplate into the
`_run_tier_round` helper from Phase A; let each escalator keep its
distinct install/install-on-failure semantics.

## Risks

| Risk | Mitigation |
|---|---|
| Subtle ordering bug in 304 reuse path | `tests/test_cache.py::test_conditional_hit` + `tests/test_fetcher.py` cover this; run full suite per phase |
| Counter ordering (`url_rewrites`, `archive_dispatches`) misplaced | Each counter is incremented at exactly one site; preserve that |
| Lost diagnostic rows | Diagnostic appends are an enumerable list — count before/after on representative tests |
| Lost event emission ordering | LDD events are testable via `app.ldd.add_sink(...)`; add a smoke test if needed |

## Sequence

Three sequential commits, each shippable on its own and gated by
`make check`:

1. **Step a — `_run_tier_round` helper.** Extract shared dispatch
   boilerplate. ~25 LOC saved. Used by both `_phase_tier_loop` and
   the two escalators.
2. **Step b — `_phase_tier_loop` split.** Introduce `_acquire_or_skip`,
   `_handle_tier_result`, `_apply_after_tier`. Outer loop becomes a
   ~30-LOC coordinator.
3. **Step c — escalator polish.** Trim `_dispatch_archive` /
   `_escalate_browser` using the Phase-A helper. Done.

## Out of scope (future work)

- Migrating `FetchContext` to a state machine — overkill for this code.
- Moving the tier registry / `TIER_ORDER` to a plugin system — would
  require a stable Tier protocol contract that 0.6+ can change.
- Decomposing `_phase_extract` — already short enough; splitting it
  buys little.

## Decision points needing input

None mechanical. The Plan can execute autonomously. If any phase
introduces a test regression that isn't an obvious typo, **stop** and
surface the test, rather than auto-rewriting until green.
