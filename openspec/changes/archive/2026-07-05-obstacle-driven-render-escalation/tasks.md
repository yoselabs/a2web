# Tasks — obstacle-driven-render-escalation

Test-first (BDD). `make check` (lint + ty + test, coverage ≥85%) is the gate.

## 1. Trigger predicate

- [x] 1.1 Test: `_obstacle_wants_render(fc)` is True only when ask-path +
      `obstacle ∈ {empty, blocked}` + `paid_dispatches < 1`; False for no-ask,
      `obstacle ∈ {paywalled, error, None}`, and when `paid_dispatches == 1`.
- [x] 1.2 Add `_obstacle_wants_render(fc) -> bool` in `fetcher.py`, importing
      `_INCOMPLETE_OBSTACLES` from `fetcher_response` (single source of truth).

## 2. Obstacle-render phase

- [x] 2.1 Test (fetch-level, stubbed tiers): an `ask` over a fat-shell page whose
      first extraction yields `obstacle: "empty"` dispatches the paid tier,
      re-extracts, and returns the rendered answer with `retrieval_incomplete`
      false and a `zyte`/paid diagnostic step.
- [x] 2.2 Test: no paid tier keyed → no render, `retrieval_incomplete` true +
      critical hint (never-silently-miss).
- [x] 2.3 Test: render produces identical/empty content → original answer kept,
      obstacle survives → `retrieval_incomplete` true; no second dispatch.
- [x] 2.4 Test: `paid_dispatches == 1` already (prior gate/handler render) →
      obstacle phase is a no-op (shared cap).
- [x] 2.5 Test: `obstacle: "paywalled"` / `"error"` → no render dispatched.
- [x] 2.6 Add `_phase_obstacle_render(fc, *, state)` in `fetcher.py`: guard via
      `_obstacle_wants_render`; snapshot `content_md`; clear
      `pre_rendered_payload`; `await _escalate_paid`; if new content →
      `_phase_extract` + `_phase_extract_answer`; else restore snapshot.

## 3. Pipeline wiring (cache-write relocation)

- [x] 3.1 Test: the no-obstacle ask/`fetch_raw` path caches identically to today
      (cache-write relocation is behavior-preserving) — assert a cache row is
      written for a healthy fetch.
- [x] 3.2 In `_run_pipeline`, insert `_phase_obstacle_render` after
      `_phase_extract_answer` and move `_phase_cache_write` to run AFTER it (final
      body cached once; shell never cached).

## 4. Regression + fail-loud

- [x] 4.1 Test: `paid_auth_error` during the obstacle render fails loud
      (authoritative verdict wins; no re-answer over stale content).
- [x] 4.2 Confirm the v0.29.0 confidence-cap / `retrieval_incomplete` behavior is
      intact for the surviving-obstacle and paywalled/error cases.

## 5. Gate + wiring

- [x] 5.1 `make check` green (lint + ty + test, coverage ≥85%, all arch fitness).
- [~] 5.2 (deferred — spends a real render+LLM; unit suite covers every branch) Live check (network, spends 1 render + LLM): an `ask` over a known
      JS-SPA page that confabulated pre-change now renders + returns real content.
      Record the URL + result in the change notes.
- [x] 5.3 CHANGELOG.md entry; version bump + `make install-global`.
