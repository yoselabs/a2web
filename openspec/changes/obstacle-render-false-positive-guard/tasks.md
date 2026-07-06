# Tasks — obstacle-render-false-positive-guard

Test-first (BDD). `make check` is the gate. (Implemented alongside the live
finding that surfaced the false positive.)

## 1. Length-independent SPA detector

- [x] 1.1 Test (`tests/packages/test_block_detector.py`): `looks_like_unrendered_spa`
      True for root-mount + `<script>` (fat or thin); False for a plain static
      page, a root mount without scripts, and scripts without a root mount.
- [x] 1.2 Add `looks_like_unrendered_spa(raw_html) -> bool` to
      `packages/block_detector.py` — `_SCRIPT_TAG_RE` AND `_JS_SHELL_ROOT_MARKERS`,
      no length gate.

## 2. Guard the obstacle-render trigger

- [x] 2.1 Test (predicate): `_obstacle_wants_render` False when tier is
      `jina`/`browser`/`browser_robust`, or when the body has no SPA markers
      (static page); True for a non-JS tier with SPA markers.
- [x] 2.2 Test (fetch-level): a static page (no markers) reporting `obstacle:
      empty` does NOT dispatch a render (no `zyte` step, one LLM call), obstacle
      survives → `retrieval_incomplete`.
- [x] 2.3 Add `_JS_EXECUTED_TIERS` + the two-part guard to `_obstacle_wants_render`
      (tier not JS-executing AND `looks_like_unrendered_spa(fc.body)`).
- [x] 2.4 Update the v0.32.0 obstacle-render tests so the shell fixture carries
      SPA markers (a real fat shell has them).

## 3. Gate + wiring

- [x] 3.1 `make check` green (lint + ty + test, coverage ≥85%, all arch fitness).
- [x] 3.2 CHANGELOG.md entry; patch version bump + `make install-global`.
