## 1. Anchor + scaffold

- [x] 1.1 Add `FIXTURES_DIR = Path(__file__).parent` to `tests/fixtures/__init__.py`.
- [x] 1.2 Create the directory tree with an `__init__.py` in each: `tests/architecture/`, `tests/utils/`, `tests/packages/` (+ `cookie_store/`, `llm_extract/`, `llm_extract/providers/`), and `tests/capabilities/` with subdirs `app_composition/`, `app_state/`, `ask_response/`, `fetch_response/`, `quality_gate/`, `tier_pipeline/`, `raw_tier/`, `browser_tier/`, `site_handlers/`, `cache/`, `extraction/`, `json_extract/`, `browser_cookies/`, `request_log/`.

## 2. Move architecture, packages, utils, contracts

- [x] 2.1 `git mv test_packages_independence.py architecture/`; re-anchor its repo-root path.
- [x] 2.2 `git mv` to `packages/`: `test_block_detector.py`, `test_browser_pool.py`, `test_extract.py`, `test_metadata.py`, `test_packages_json_in_script.py`.
- [x] 2.3 `git mv` to `packages/cookie_store/`: `test_cookie_store_chrome_decrypt.py`, `test_cookie_store_firefox.py`.
- [x] 2.4 `git mv` to `packages/llm_extract/`: `test_llm_cache.py`, `test_llm_judge.py`, `test_llm_module.py`; to `packages/llm_extract/providers/`: `test_llm_claude_code_provider.py`.
- [x] 2.5 `git mv test_fmt_dur.py utils/`; `git mv test_contracts.py contracts/`.

## 3. Move capability tests

- [x] 3.1 `git mv` to `capabilities/app_composition/`: `test_app_composition.py`, `test_settings.py`, `test_resources.py`. To `capabilities/app_state/`: `test_app_state.py`.
- [x] 3.2 `git mv` to `capabilities/ask_response/`: `test_ask_response.py`, `test_fetcher_ask.py`. To `capabilities/fetch_response/`: `test_fetch_response.py`, `test_models.py`.
- [x] 3.3 `git mv` to `capabilities/tier_pipeline/`: `test_fetcher.py`, `test_after_tier_execution.py`, `test_archive_escalation.py`, `test_browser_escalation.py`, `test_archive_tier.py`, `test_jina_tier.py`, `test_playbook.py`, `test_domain.py`, `test_link_discovery_composition.py`.
- [x] 3.4 `git mv` to `capabilities/raw_tier/`: `test_raw_tier.py`. To `capabilities/browser_tier/`: `test_browser_tier.py`, `test_browser_scroll_retry.py`.
- [x] 3.5 `git mv` to `capabilities/site_handlers/`: `test_handlers.py`, `test_handlers_arxiv.py`, `test_handlers_github.py`, `test_handlers_wikipedia.py`, `test_hn_front_page.py`, `test_site_handler_tier.py`.
- [x] 3.6 `git mv` to `capabilities/cache/`: `test_cache.py`. To `capabilities/extraction/`: `test_extraction_eval.py`, `test_llm_eval_suite.py`, `test_llm_eval_systems.py`, `test_max_content_chars.py`.
- [x] 3.7 `git mv` to `capabilities/json_extract/`: `test_json_synth_browser_tier.py`, `test_json_synth_integration.py`. To `capabilities/request_log/`: `test_otel_sink.py`.
- [x] 3.8 `git mv` to `capabilities/browser_cookies/`: `test_cookie_jar.py`, `test_cookie_redaction.py`, `test_cookies_refresh_tool.py`, `test_fetcher_with_cookies.py`, `test_tier_cookies.py`.

## 4. Merges

- [x] 4.1 Merge `test_proxy_pool.py` + `test_proxy_policy.py` → `packages/test_proxy_routing.py` (union imports, concatenate test bodies, no logic change); delete the two sources.
- [x] 4.2 `git mv test_gate.py packages/` — it tests the pure `block_detector.evaluate` classifier, so it belongs in the packages zone, not merged.
- [x] 4.3 Merge `test_gate_jina_paywall.py` + `test_gate_thin_browser.py` → `capabilities/quality_gate/test_gate.py` (both test the `fetcher.evaluate` domain wrapper); delete the two sources.

## 5. Path-anchor fixups

- [x] 5.1 In the 15 files using `_FIX = Path(__file__).parent / "fixtures"` (`test_extract`, `test_fetch_response`, `test_ask_response`, `test_handlers_github`, `test_fetcher_ask`, `test_hn_front_page`, `test_gate`, `test_handlers_arxiv`, `test_json_synth_browser_tier`, `test_json_synth_integration`, `test_fetcher`, `test_handlers_wikipedia`, `test_metadata`, `test_packages_json_in_script`, `test_handlers`) replace the recomputation with `from tests.fixtures import FIXTURES_DIR`.
- [x] 5.2 In `contracts/test_contracts.py` re-anchor `_GOLDEN_DIR` and `_FIX` to the moved location and `FIXTURES_DIR`.

## 6. Wire-up + verify

- [x] 6.1 Update the `bless-contracts` Makefile target: `tests/test_contracts.py` → `tests/contracts/test_contracts.py`.
- [x] 6.2 Run `pytest tests/ --collect-only -q` before and after — confirm identical collected-test count.
- [x] 6.3 Ran the gate: lint ✓, `ty` ✓, suite ✓ — **573 passed in 13.24s** (572 reorg baseline + the new aiosqlite guard), coverage 87.64%, and the pytest process **exits cleanly**.

## 7. Fix the aiosqlite interpreter-shutdown hang

- [x] 7.1 Root cause: aiosqlite >=0.21 (installed 0.22.1) creates each connection's worker thread as **non-daemon**; a `SqliteResource` opened by a test outside the a2kit `async with app:` lifecycle is never closed, so its worker thread parks forever and `threading._shutdown()` hangs the interpreter at exit. Pre-existing — it hangs every single-process run; `pytest-xdist` masked it by reaping worker subprocesses. Not caused by the reorg.
- [x] 7.2 `tests/conftest.py` patches `aiosqlite.core.Connection.__init__` to daemonize the worker thread for the test process only. Test DBs are throwaway temp / in-memory files with no exit-durability need; production keeps the non-daemon default and closes via `SqliteResource.__aexit__`.
- [x] 7.3 `tests/architecture/test_aiosqlite_daemon.py` guards the patch — fails loudly if the daemonize is ever removed.
