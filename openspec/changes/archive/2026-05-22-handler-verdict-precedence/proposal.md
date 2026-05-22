## Why

When a site handler returns `Verdict.not_found` — the strongest negative signal in the pipeline, meaning the site expert confirmed the content is gone — the orchestrator continues the tier cascade anyway. For sites that serve HTTP 200 + a thin SPA shell for deleted content (Reddit returns 200 for deleted posts), the raw tier "wins" with `Verdict.ok`, the quality gate then downgrades it to `length_floor`, and the handler's authoritative `not_found` is silently overwritten. The agent receives `status=failed, length_floor, confidence=low` — which reads as a transient extraction glitch worth retrying — instead of `not_found`, which means "definitively gone, do not retry."

This was proven by probe: the deleted Reddit post `/r/programming/comments/1ka1bxv/…` — handler `.json` 404 + `old.reddit` 404 → handler `not_found`; then raw 200 + 8 KB SPA shell → gate `length_floor`. A live Reddit thread succeeds cleanly via the same handler, so the handler is correct; the bug is verdict precedence in `fetcher.py`.

## What Changes

- A site handler's terminal `Verdict.not_found` SHALL survive the tier cascade. When a site handler returns `not_found` AND the fetch ultimately fails (no tier produces gate-passing content), the final response verdict SHALL be `not_found`, not whatever vaguer verdict (`length_floor`, `other`) a downstream generic tier produced.
- When a downstream tier DOES produce real, gate-passing content, the success stands unchanged — the precedence rule applies only on failure. It never clobbers a genuine recovery.
- Scope is strictly `not_found` — the one handler verdict with unambiguous "definitive, do not retry" semantics and a proven repro.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `tier-pipeline`: adds an orchestrator verdict-handling rule — a site handler's terminal `not_found` takes precedence over a downstream tier's failure verdict when the fetch fails.

## Impact

- `src/a2web/fetcher.py` — one `FetchContext` field (`handler_not_found`), one line in `_phase_tier_loop` to set it, one small reconciliation phase in `_run_pipeline`.
- Tests under `tests/capabilities/tier_pipeline/`.
- No wire/envelope shape change — `not_found` is an existing `Verdict` and `FetchStatus.failed` is unchanged; only the verdict *value* on a failed fetch becomes more accurate.
- No dependency change.

**Out of scope:** the ~12 s archive dispatch on a deleted Reddit post (correct-by-design — Wayback may hold a pre-deletion snapshot); transient handler verdicts (`rate_limited` / `timeout` / `connection_error`) — different semantics, no repro; the broader "`length_floor` is a dead-end verdict" question (no live repro); benchmark corpus fixture refresh (separate benchmark-maintenance task).
