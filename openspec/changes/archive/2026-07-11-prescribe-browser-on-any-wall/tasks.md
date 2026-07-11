## 1. Grounding

- [x] 1.1 Confirm the three current `try_user_browser` emission sites in `_phase_gate_and_escalate` (render_requested branch, transport `_is_escalatable_transport_wall`, late `_WALL_VERDICTS`) and the early-return at `fetcher.py:1668` that forces the split.
- [x] 1.2 Confirm the `retrieval_incomplete` derivation in `fetcher_response.py` (the wall-verdict tuple ~line 289 + the "failed + try_user_browser" hook ~line 332) and that `status = failed` for every non-`ok` verdict.
- [x] 1.3 Confirm how authoritative `not_found` is detected (`any(o.authoritative and o.verdict is Verdict.not_found for o in fc.observations)`) and that `_has_browser_hint` dedup exists.

## 2. Systematic emission

- [x] 2.1 Add `_is_genuine_gone(fc) -> bool`: True for `resolved_verdict in (dns_error, content_type_mismatch)`, authoritative `not_found`, or `paid_auth_error` (paid keeps its own hint). Keep it a pure read over `fc`.
- [x] 2.2 Add `_prescribe_browser_on_wall(fc)`: `if fc.resolved_verdict() is not Verdict.ok and not _is_genuine_gone(fc) and not _has_browser_hint(fc): fc.operator_hints.append(try_user_browser_hint(fc.final_url))`.
- [x] 2.3 Call `_prescribe_browser_on_wall(fc)` once at the end of `_run_pipeline`, AFTER `_phase_gate_and_escalate` returns, so it runs for both the bodyless early-return path and the body-bearing path.

## 3. Delete the whitelists

- [x] 3.1 Remove the three in-phase `try_user_browser` emission blocks in `_phase_gate_and_escalate` (render_requested, transport, late `_WALL_VERDICTS`).
- [x] 3.2 Delete `_WALL_VERDICTS`, `_ESCALATABLE_TRANSPORT_VERDICTS`, and `_is_escalatable_transport_wall` (now unused). Keep the Reddit handler's eager hint + `_has_browser_hint`.
- [x] 3.3 Grep for any remaining reference to the deleted symbols (tests, imports) and reconcile.

## 4. retrieval_incomplete follows the hint

- [x] 4.1 In `fetcher_response.py`, derive `retrieval_incomplete` from "failed + `try_user_browser` hint present" (existing hook) PLUS `paid_auth_error`. Remove the now-redundant wall-verdict tuple so there is a single source of truth.
- [x] 4.2 Confirm genuine-gone terminals (`dns_error`, authoritative `not_found`, `content_type_mismatch`) end `failed` but NOT `retrieval_incomplete` and carry NO `try_user_browser`.

## 5. Tests

- [x] 5.1 Add/adjust unit + e2e tests: each content wall, each transport verdict, `length_floor`, `proxy_unavailable`, `other` → `failed` + `retrieval_incomplete` + `try_user_browser`.
- [x] 5.2 The motivating case: a fetch that goes 403 (upstream) → thin body → `length_floor` ends with the `try_user_browser` hint (previously bare).
- [x] 5.3 Genuine-gone: `dns_error` and authoritative `not_found` → `failed`, NO hint, NOT `retrieval_incomplete`. `content_type_mismatch` → no `try_user_browser`. `paid_auth_error` → `paid_auth_error` hint + `retrieval_incomplete`, not `try_user_browser`.
- [x] 5.4 Single-emission + dedup: a bodyless transport failure and a body-bearing wall each emit exactly once; a Reddit eager hint is not duplicated.
- [x] 5.5 Update existing tests that asserted a now-covered failed verdict carries no hint (legitimate expectation changes — verify each reflects real desired behavior, not a fixture hack).

## 6. Verification

- [x] 6.1 Run `make check` (lint + ty + full test + coverage ≥85%) and `make arch`.
- [x] 6.2 Update `fetcher` / `fetcher_response` docstrings + comments to describe the single systematic floor and the genuine-gone blacklist (retire the whitelist language).
- [x] 6.3 Live sanity (native browser now available): re-fetch `g2.com/categories/crm` via `fetch_raw` and confirm the `length_floor`-after-403 terminal now carries `try_user_browser` + `retrieval_incomplete`, then confirm opening the same URL in the real browser returns the full content (the prescription is correct).
