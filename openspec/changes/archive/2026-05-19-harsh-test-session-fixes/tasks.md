## 1. JSON-in-script extractor (new package)

- [x] 1.1 Create `src/a2web/packages/content_extract/json_in_script.py` with `JsonPayload` dataclass and `extract_json_payloads(html: str) -> list[JsonPayload]`
- [x] 1.2 Implement detectors for `__NEXT_DATA__`, `__NUXT_DATA__`, `application/ld+json`, generic `application/json` script tags using `selectolax`
- [x] 1.3 Implement `rank_payloads(payloads) -> list[JsonPayload]` preferring LD-JSON `Product`/`Article`/`ItemList` with ≥3 populated fields
- [x] 1.4 Add Gherkin scenarios as docstring at module top per BDD-first convention
- [x] 1.5 Add fixtures: `tests/fixtures/trendyol_search_next_data.html`, `tests/fixtures/yandex_market_generic.html`, `tests/fixtures/ld_json_product.html`
- [x] 1.6 Write `tests/test_packages_json_in_script.py` covering all spec scenarios
- [x] 1.7 Verify `tests/test_packages_independence.py` still passes (no domain imports)

## 2. JSON synthesis at the a2web seam

- [x] 2.1 Add `json_to_markdown_rows(payload: JsonPayload) -> str` to `src/a2web/domain.py` — converts ranked payload to a markdown table; only handles known shapes (LD-JSON Product/Article/ItemList, Next.js pageProps.products / pageProps.items)
- [x] 2.2 Add `count_sentences(text: str) -> int` helper to `domain.py` (or wherever pure helpers live) for the trafilatura-thin trigger
- [x] 2.3 Wire JSON path into `_phase_extract` in `src/a2web/fetcher.py`: when trafilatura output is `<2_048 chars` OR `count_sentences < 3`, call extractor + ranker + synthesis; replace `content_md` only if synthetic ≥2× original
- [x] 2.4 Emit `StageStarted("json_synth")` / `StageEnded("json_synth", verdict="replaced"|"kept_original"|"no_payloads")` LDD events
- [x] 2.5 Tests: `tests/test_json_synth_integration.py` — Trendyol fixture replaces, SSR fixture keeps original, low-yield JSON keeps original

## 3. Paywall classifier — jina stub recognition

- [x] 3.1 Locate the current gate classifier module (search for `Verdict.length_floor` assignment paths)
- [x] 3.2 Add the jina-stub rule: when `tier == "jina"` AND `len(body) < 2_048` AND `re.search(r"Target URL returned error 40[13]", body)` → `Verdict.paywall`, `subsystem = "jina_stub"`
- [x] 3.3 Tests: `tests/test_gate_jina_paywall.py` — NYT-shape 403 stub, WSJ-shape 401 stub, long jina response with quoted `error 403` substring (must NOT fire)
- [x] 3.4 Integration test: end-to-end via `fetcher.fetch()` against a recorded jina-stub fixture, assert archive tier dispatches

## 4. Thin-browser-response heuristic

- [x] 4.1 Add `JS_HEAVY_HOSTS: frozenset[str]` constant to the gate module with seed: `x.com`, `twitter.com`, `instagram.com`, `tiktok.com`, `trendyol.com`, `aliexpress.com`
- [x] 4.2 Read optional comma-separated override from `AppSettings.js_heavy_hosts_extra` (new `A2WEB_JS_HEAVY_HOSTS` env var) and union with the seed set
- [x] 4.3 Add rule: when `tier == "browser"` AND `status == 200` AND `len(body) < 1_024` AND host in `JS_HEAVY_HOSTS` → `Verdict.length_floor`
- [x] 4.4 Tests: X.com noscript stub triggers length_floor; non-listed host keeps normal verdict; override-via-env adds host

## 5. Browser tier: scroll-on-thin retry

- [x] 5.1 In `src/a2web/tiers/browser.py`, after the initial `page.goto(..., wait_until="networkidle")`, capture html length; if `<4_096` AND host in `JS_HEAVY_HOSTS`, run scroll retry
- [x] 5.2 Implement scroll retry: `await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")` → `await page.wait_for_load_state("networkidle", timeout=2_000)` → re-capture
- [x] 5.3 Wrap scroll retry in `try`/`except` (PlaywrightTimeoutError) → fall back to initial capture; never raise from the retry path
- [x] 5.4 Emit `StageStarted("browser_scroll_retry")` / `StageEnded("browser_scroll_retry", verdict="larger"|"smaller"|"timeout")` LDD events
- [x] 5.5 Tests: `tests/test_browser_scroll_retry.py` using a fake page that returns thin HTML pre-scroll and richer HTML post-scroll; timeout case; non-thin first-capture skips retry

## 6. Camoufox subprocess stderr capture

- [x] 6.1 1h spike: identify the stderr-capture knob — examined `camoufox.async_api.AsyncCamoufox` + playwright launch path; documented in `docs/history/spike-camoufox-stderr-2026-05-19.md`
- [x] 6.3 Spike found NO supported knob. Skipping implementation; documented in spike doc + cycle feedback. 6.2/6.4/6.5 deferred (would require fork/monkey-patch).

## 7. `--max-content-chars` CLI / MCP flag

- [x] 7.1 Add `max_content_chars: int | None` field to `FetchContext` (`src/a2web/fetcher.py`)
- [x] 7.2 Add `max_content_chars: int | None = None` param to `fetch()` orchestrator; plumb into `FetchContext` on construction
- [x] 7.3 Add `Annotated[int | None, pydantic.Field(description="Cap content chars sent to extractor LLM. Default: 100000.")]` to both `fetch` and `fetch_raw` in `src/a2web/routers.py`
- [x] 7.4 In `LlmExtractorResource.extract()`, accept override and pass to `Extractor.extract()` — may require adding a per-call override at the extractor level (today only at construction)
- [x] 7.5 Update extractor to accept per-call override (modify `Extractor.extract()` signature to take optional `max_content_chars`; falls back to instance default)
- [x] 7.6 Tests: CLI flag honored end-to-end (fixture page with 200K chars, flag=50000 → `tokens.full` reflects cap); flag absent → default behavior; MCP kwarg matches CLI

## 8. Documentation + release

- [x] 8.1 Update `CHANGELOG.md` with `## [Unreleased]` entries for each of the six fixes
- [x] 8.2 Update `README.md` `--max-content-chars` mention under the `ask` tool section
- [x] 8.3 Update `docs/history/A2KIT_FEEDBACK_v0.39.md` (or current cycle) with the camoufox stderr finding if upstream
- [x] 8.4 Re-run harsh-test bench: `/tmp/a2web-bench-backpacks/findings.md` updated with post-fix numbers for Trendyol, NYT, TechCrunch, Yandex Market

## 9. Quality gate

- [x] 9.1 `make check` — lint + ty + test, coverage ≥85%
- [x] 9.2 `tests/test_packages_independence.py` green
- [x] 9.3 Manual smoke: `a2web web ask --url https://www.trendyol.com/sr?q=sirt+cantasi` returns top-10 with prices (JSON path fired)
- [x] 9.4 Manual smoke: `a2web web ask --url https://www.nytimes.com/<some-paywalled-article>` returns archive content (paywall classifier + archive escalation fired)
- [x] 9.5 Manual smoke: stderr capture — TechCrunch fetch prints no Node.js trace to terminal
