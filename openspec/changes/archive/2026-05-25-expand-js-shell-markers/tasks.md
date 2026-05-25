## 1. Marker regex expansion

- [x] 1.1 In `src/a2web/packages/block_detector.py`, extend `_JS_SHELL_ROOT_MARKERS` regex with three new alternations after `<noscript`: `name="js_challenge"` and `name="jsc_orig_r"` (Reddit JS-challenge interstitial) and `<[a-z][a-z0-9]*-[a-z][a-z0-9-]*` (generic custom element). Preserve `re.IGNORECASE`.
- [x] 1.2 Verify there is no other code path that ALSO reads `_JS_SHELL_ROOT_MARKERS` — it is consumed only inside `evaluate(...)`. No other change needed.

## 2. Tests

- [x] 2.1 In `tests/packages/test_block_detector.py`, add `test_reddit_js_challenge_marker_triggers_browser_escalation`: synthetic raw_html with the Reddit-shaped hidden form (`name="js_challenge"`, `name="jsc_orig_r"`) + `<script>` + `content_md` below length floor; assert `verdict == BlockVerdict.length_floor`, `subsystem == "js_required"`, `suggested_tier == "browser"`.
- [x] 2.2 Add `test_generic_custom_element_marker_triggers_browser_escalation`: synthetic raw_html with `<my-widget>...<script>...` (no React/Vue/Next markers, no challenge form); same assertions.
- [x] 2.3 Add `test_hyphenated_attributes_alone_do_not_trigger`: synthetic raw_html with `data-foo="x-y-z"` / `class="my-cmp"` but NO hyphenated tag names AND no challenge form; assert no `suggested_tier` (custom-element regex must not match attribute values).
- [x] 2.4 Add `test_above_length_floor_with_custom_elements_is_ok`: synthetic raw_html with substantial body (above floor) containing custom elements; assert `verdict == BlockVerdict.ok` (progressive-enhancement case).
- [x] 2.5 Add `test_generic_solution_field_alone_does_not_trigger`: synthetic thin raw_html with `<input name="solution">` but NO `js_challenge` / `jsc_orig_r` / custom-element / React markers; assert no `suggested_tier` (generic "solution" field name must not be enough on its own — false-positive guard for legitimate quiz sites).
- [x] 2.6 Add a Reddit-shaped fixture at `tests/fixtures/reddit_shreddit_shell.html` (the real ~8KB JS-challenge body captured from `https://www.reddit.com/r/LocalLLaMA/`); add a test that loads it and asserts `suggested_tier == "browser"`.

## 3. Gates

- [x] 3.1 `make lint` passes.
- [x] 3.2 `make ty` passes.
- [x] 3.3 `make test` passes with ≥85% coverage.
- [x] 3.4 `make check` passes end-to-end.

## 4. Validation

- [ ] 4.1 Re-run the bench (`make bench`) and confirm `reddit-listing` no longer reports `tier=raw verdict=length_floor`. Expected: tier=browser, verdict=ok, real DOM extracted. (LIVE-NETWORK + LLM QUOTA — user-triggered.)
- [ ] 4.2 Spot-check at least one non-Reddit web-component SPA (if findable in corpus) — confirm it also escalates.

## 5. Documentation + backlog hygiene

- [x] 5.1 Update `CHANGELOG.md` with a `## [Unreleased]` entry under v0.22 (or appropriate next version): "Quality gate now recognizes (a) Reddit JS-challenge interstitials via `js_challenge` / `jsc_orig_r` form-field markers, and (b) any web-component SPA shell via a generic custom-element regex (per HTML5 spec). Both route to browser-tier escalation. Fixes Reddit listings returning `length_floor` on raw tier."
- [x] 5.2 Update `BACKLOG.md`: close the "Reddit `old.reddit.com` raw-tier fetch failure (2026-05-24)" item with a "✅ fixed via expand-js-shell-markers (2026-05-25); root cause was upstream marker gap, not the handler." Add a new item: "🟢 Investigate `403 → browser` planner escalation rule when a probe finds a site with `raw=403 ∧ browser=200`. Current probe found none — Cloudflare 403 already bypassed by `curl_cffi impersonate=chrome`."
- [x] 5.3 Update `CLAUDE.md` if the block-detector contract paragraph mentions marker scope (verify; small edit if needed).

## 6. Archive

- [ ] 6.1 Run `openspec archive expand-js-shell-markers` after merge to apply the delta to canonical specs and move the change into `openspec/changes/archive/`.
