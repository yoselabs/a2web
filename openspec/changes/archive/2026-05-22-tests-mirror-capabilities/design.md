## Context

`tests/` holds 60 flat `test_*.py` files plus `conftest.py`, `fixtures/`, and `contracts/`. `src/a2web/` is layered and the project is spec-driven (`openspec/specs/` has 17 capabilities). The flat test tree cannot express the `packages/` independence boundary, gives no spec→test mapping, and mixes pure unit tests with full-orchestrator integration tests. This change is a pure regrouping; the test logic is sound.

Import analysis classified every file by whether it touches a domain module (`fetcher`, `routers`, `state`, `server`, `domain`, `cookie_jar`, `llm_resource`, `tiers`, `handlers`, `actions`, `events`, `llm_eval`) or imports only `a2web.packages.*`.

## Goals / Non-Goals

**Goals:**
- A three-zone test tree whose structure makes the codebase's architecture and the OpenSpec capability set legible.
- A deterministic, checkable rule for where any new test file belongs.
- History-preserving moves (`git mv`); zero behavior change; the suite passes identically before and after.

**Non-Goals:**
- Speed. Test wall-time is unaffected (`pytest tests/` discovers recursively either way). Speed is a separate concern.
- Rewriting test logic, splitting unit/integration by marker, or changing `--cov` config.
- Touching `src/`, dependencies, or any wire/API surface.

## Decisions

### Three zones, not a strict `src/` mirror

A strict 1:1 `src/` mirror is impossible: `quality-gate` is a real capability smeared across `fetcher.py`, `fetcher_response.py`, and `models.py` with no home module; 11 files drive the whole `fetcher.fetch()` orchestrator and belong to no single module. So the tree has three zones:

- `tests/architecture/` — meta-tests asserting invariants about the codebase itself.
- `tests/packages/` — tests importing **only** `a2web.packages.*` (+ `models`/`settings`/`utils`), mirroring `src/a2web/packages/`. These honor the same no-domain-import rule the package code does.
- `tests/capabilities/<capability>/` — one directory per OpenSpec capability, holding domain-coupled behavior tests. A capability directory verifies its `openspec/specs/<capability>/spec.md`.

Plus the existing `tests/contracts/` (golden JSON + its test) and a new `tests/utils/` mirroring `src/a2web/utils/`.

**Placement rule:** meta-test → `architecture/`; imports only `a2web.packages.*` → `packages/` (sub-pathed to mirror the package); otherwise → the `capabilities/<cap>/` whose spec the test most directly verifies. Capability over module because the project is spec-driven — when a delta spec is written, the test directory is mechanically known, and the grouping survives `src/` refactors.

**Alternative considered:** group by `src/` module — rejected (no home for `quality-gate` or integration tests, and tests churn on every module refactor). Group by `unit`/`integration` — rejected here (that is the separate speed change; it answers "how fast?" not "verifies what?").

### Capabilities with no own test home

`tier-pipeline` absorbs `jina_tier`, `archive_tier`, escalations, the playbook, and `domain.py`'s captcha rewrite — there is no `jina-tier`/`archive-tier` capability. `proxy-pool` has only pure-package tests, which live in `packages/`; no `capabilities/proxy_pool/` directory is created. `streaming-progress` and `release-artifacts` have no current test; no empty directory is created. Directories are created only where a test lands.

### Fixture-path anchoring

15 files compute `_FIX = Path(__file__).parent / "fixtures"`; `test_contracts.py` and `test_packages_independence.py` compute `contracts/` and a repo-root anchor the same way. Moving a file deeper breaks this math. Fix: `tests/fixtures/__init__.py` exposes `FIXTURES_DIR = Path(__file__).parent`; moved files import it instead of recomputing. `test_packages_independence.py` derives the repo root from a stable anchor. This is the only content edit to moved files and is mechanical — no assertion changes.

### `__init__.py` per directory

Every new test directory gets an `__init__.py`, consistent with the existing `tests/__init__.py` and `tests/fixtures/__init__.py`. With `tests/` already a package, pytest's `prepend` import mode then resolves subdirectories cleanly and `from tests.fixtures import FIXTURES_DIR` works (repo root is on `sys.path`).

### Full file mapping

| Current file | Destination |
|---|---|
| test_packages_independence.py | architecture/test_packages_independence.py |
| test_block_detector.py | packages/test_block_detector.py |
| test_browser_pool.py | packages/test_browser_pool.py |
| test_extract.py | packages/test_extract.py |
| test_metadata.py | packages/test_metadata.py |
| test_packages_json_in_script.py | packages/test_packages_json_in_script.py |
| test_gate.py | packages/test_gate.py (pure `block_detector.evaluate` test) |
| test_proxy_pool.py + test_proxy_policy.py | packages/test_proxy_routing.py **(merge)** |
| test_cookie_store_chrome_decrypt.py | packages/cookie_store/test_cookie_store_chrome_decrypt.py |
| test_cookie_store_firefox.py | packages/cookie_store/test_cookie_store_firefox.py |
| test_llm_cache.py | packages/llm_extract/test_llm_cache.py |
| test_llm_judge.py | packages/llm_extract/test_llm_judge.py |
| test_llm_module.py | packages/llm_extract/test_llm_module.py |
| test_llm_claude_code_provider.py | packages/llm_extract/providers/test_llm_claude_code_provider.py |
| test_fmt_dur.py | utils/test_fmt_dur.py |
| test_contracts.py | contracts/test_contracts.py |
| test_app_composition.py, test_settings.py, test_resources.py | capabilities/app_composition/ |
| test_app_state.py | capabilities/app_state/ |
| test_ask_response.py, test_fetcher_ask.py | capabilities/ask_response/ |
| test_fetch_response.py, test_models.py | capabilities/fetch_response/ |
| test_gate_jina_paywall.py + test_gate_thin_browser.py | capabilities/quality_gate/test_gate.py **(merge)** |
| test_fetcher.py, test_after_tier_execution.py, test_archive_escalation.py, test_browser_escalation.py, test_archive_tier.py, test_jina_tier.py, test_playbook.py, test_domain.py, test_link_discovery_composition.py | capabilities/tier_pipeline/ |
| test_raw_tier.py | capabilities/raw_tier/ |
| test_browser_tier.py, test_browser_scroll_retry.py | capabilities/browser_tier/ |
| test_handlers.py, test_handlers_arxiv.py, test_handlers_github.py, test_handlers_wikipedia.py, test_hn_front_page.py, test_site_handler_tier.py | capabilities/site_handlers/ |
| test_cache.py | capabilities/cache/ |
| test_extraction_eval.py, test_llm_eval_suite.py, test_llm_eval_systems.py, test_max_content_chars.py | capabilities/extraction/ |
| test_json_synth_browser_tier.py, test_json_synth_integration.py | capabilities/json_extract/ |
| test_cookie_jar.py, test_cookie_redaction.py, test_cookies_refresh_tool.py, test_fetcher_with_cookies.py, test_tier_cookies.py | capabilities/browser_cookies/ |
| test_otel_sink.py | capabilities/request_log/ |

## Risks / Trade-offs

- **A moved file's fixture path silently resolves wrong** → all 17 path-dependent files switch to the `FIXTURES_DIR` anchor in the same step they move; the full suite is run after the move and any broken path fails loudly.
- **`bless-contracts` Makefile target breaks** (hardcodes `tests/test_contracts.py`) → update the target to `tests/contracts/test_contracts.py` in the same change.
- **Merged files lose a failing test in a dedup mistake** → before/after test counts are compared; the merge concatenates test bodies and unions imports only, no logic edits.
- **`git mv` + content edit obscures history** → moves and the one-line anchor edit are acceptable; `git log --follow` still works through a rename-with-small-edit.
- **A capability assignment is debatable** (e.g. `test_fetcher_ask` → `ask_response` vs `tier_pipeline`) → the mapping table is the single source of truth; a wrong guess is one `git mv` to correct later, not a structural flaw.

## Migration Plan

1. Add `FIXTURES_DIR` to `tests/fixtures/__init__.py`.
2. Create the directory tree with `__init__.py` files.
3. `git mv` each file per the mapping; apply the path-anchor edit to the 17 affected files.
4. Perform the two merges; delete the now-empty source files.
5. Update the `bless-contracts` Makefile target.
6. Run `make check`; confirm the same test count and a passing suite.

Rollback: `git revert` the single commit — moves and edits are self-contained.
