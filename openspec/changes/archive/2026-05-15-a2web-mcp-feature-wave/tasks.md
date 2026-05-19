# Tasks — a2web MCP feature wave

Prereq: `2026-05-15-a2kit-v038-migration` is landed and `make check` is green on main.

Three feature blocks. Order within blocks is load-bearing; blocks themselves are independent and can be parallelized if multiple hands are working.

---

## Block 1 — Reddit search URL handler

- [ ] 1a. `src/a2web/handlers/reddit.py` — add new regex alongside `_COMMENTS_PATH_RE`:
  ```python
  _SEARCH_PATH_RE = re.compile(r"^(/r/[^/]+)?/search/?$")
  ```
  Matches both subreddit-scoped (`/r/projectors/search/`) and unscoped (`/search/`).

- [ ] 1b. Add `_url_shape(url: str) -> Literal["comments", "permalink", "search"]` helper that classifies the URL once. Used by both `matches()` and `fetch()` to avoid duplicating the regex match.

- [ ] 1c. Extend `RedditHandler.matches(url)` to return True when `_SEARCH_PATH_RE` matches. Existing `_COMMENTS_PATH_RE` match path stays.

- [ ] 1d. Add `_render_search(payload: Any, *, query: str) -> dict[str, Any]` in `reddit.py`. Consumes a Reddit search Listing (single `kind: "Listing"` with `t3` children — NOT the `[post, comments]` two-element pair). Output shape per design.md Decision 2:
  - H1 heading: `# Search: {query}`
  - H2 heading: `## Results ({n})`
  - Body: one line per `t3` post: `- **{title}** (r/{subreddit} · u/{author}, score {score}, {n} comments, {age}) <permalink>`
  - Empty `Listing` → return `{"is_empty": True, "content_md": "", ...}` (matches `_empty_render` shape).
  - Cap at 25 entries.

- [ ] 1e. Add `human_age(seconds_ago: float) -> str` helper. Returns `"3d"`, `"2y"`, `"5h"` etc. Place in `reddit.py` for now; if reused elsewhere later, move to `domain.py`.

- [ ] 1f. `RedditHandler.fetch()` dispatches rendering by URL shape:
  - `_url_shape(url) == "search"` → `_render_search(payload, query=parsed_query)`
  - `_url_shape(url) in {"comments", "permalink"}` → existing `_render_thread(...)` path
  - Permalink focus and crosspost handling stay scoped to thread rendering.

- [ ] 1g. Extract `query` from the URL's `?q=` parameter at the top of `fetch()`. Pass through to `_render_search` via kwarg.

- [ ] 1h. URL rewrite: confirm `_to_json_url(url)` produces `/r/projectors/search.json?q=...` from `/r/projectors/search/?q=...` (the existing trailing-`/` → `.json` rewrite already covers this — verify in unit test).

- [ ] 1i. Error handling: search URLs share the existing error-translation table (`403` → `forbidden`, `429` → `rate_limited`, `≥400` → `connection_error`). NO archive escalation for search URLs (Wayback doesn't usefully cache dynamic search pages) — return `_empty_result(url, Verdict.not_found)` without the archive hint.

- [ ] 1j. `tests/test_handlers.py` — add Reddit search test cases:
  - `test_reddit_search_subreddit_scoped` — mock httpx response with a real captured `search.json` payload (15+ results), assert `_render_search` returns markdown with H1, H2, ≥10 list entries.
  - `test_reddit_search_unscoped` — unscoped `/search/?q=...` produces correct URL rewrite + render.
  - `test_reddit_search_empty_results` — empty Listing returns `no_match=True`.
  - `test_reddit_search_403` — handler translates to `Verdict.forbidden` without archive escalation.

- [ ] 1k. `make check` green.

---

## Block 2 — Captcha-redirect pre-routing

- [ ] 2a. Decide host of the new pure function:
  - If `domain.py` is currently under ~150 lines: add `rewrite_captcha_host(url: str) -> str | None` there.
  - If `domain.py` is approaching density: new file `src/a2web/captcha_routing.py` with the pure function + the known-host frozenset.
  Pick during implementation; the import path in `fetcher.py` adjusts accordingly.

- [ ] 2b. Implement `rewrite_captcha_host(url: str) -> str | None`:
  - Known-host frozenset: `{"google.com", "www.google.com", "bing.com", "www.bing.com"}`. Only the `/search` path triggers rewrite; other Google subpaths (Maps, Drive shared links, etc.) are passed through unchanged.
  - Extract `q` parameter from input URL. Discard everything else (tbm, start, num, hl).
  - Return `f"https://duckduckgo.com/html/?q={urllib.parse.quote(q)}"`.
  - Returns `None` when host doesn't match OR path isn't `/search`.

- [ ] 2c. `src/a2web/fetcher.py` — add captcha-rewrite step at the top of `orchestrate(...)`, before tier dispatch:
  ```python
  rewritten = rewrite_captcha_host(url)
  if rewritten is not None:
      await a2kit.ldd.event(StageStarted(t_ms=..., step="url_rewrite_captcha"))
      fc.original_url = url
      url = rewritten
      fc.url_rewrites += 1
      await a2kit.ldd.event(StageEnded(t_ms=..., step="url_rewrite_captcha"))
  ```
  Respect the playbook's `url_rewrites` cap (today 2 per fetch). The captcha rewrite counts.

- [ ] 2d. Add `original_url: str | None = None` field on `FetchContext`. Populated only when a URL rewrite occurred.

- [ ] 2e. Add `original_url` field on `FetchResponse` (top-level pydantic model) — populated from `fc.original_url` at response-build time. Documents to the caller "you asked for X, I fetched Y, here's why" via diagnostics.

- [ ] 2f. `src/a2web/packages/block_detector.py` — add second-line defense pattern set:
  - Google captcha markers: `/sorry/index` in final URL, "Our systems have detected unusual traffic" in body.
  - Bing captcha markers: similar shape — investigate during implementation.
  - When matched: emit `Verdict.block_page_detected` with `OperatorHint(code="captcha_redirect", message="Search engine captcha; consider DDG/Brave directly")`.

- [ ] 2g. `tests/test_fetcher.py` — add cases:
  - `test_captcha_rewrite_google_search` — mock orchestrator with Google search URL, assert URL is rewritten before tier dispatch, `original_url` preserved on response.
  - `test_captcha_rewrite_bing_search` — same shape for Bing.
  - `test_captcha_rewrite_preserves_non_search_google_urls` — Google Maps / Drive URL passes through unchanged.
  - `test_captcha_rewrite_respects_budget` — when `fc.url_rewrites` already at cap, captcha rewrite is skipped (per the playbook contract).

- [ ] 2h. `tests/test_handlers.py` or new test file — test `rewrite_captcha_host` purely:
  - Each host in the registry → correct DDG rewrite.
  - Non-matching hosts → `None`.
  - Missing `?q=` → `None` (no useful rewrite target).
  - URL-encoded `q` values round-trip correctly.

- [ ] 2i. `make check` green.

---

## Block 3 — LLM extras promoted to core

This block lands LAST per design.md sequencing — measure the migration's `Lazy[LlmExtractorResource]` cold-start effect before stacking the install-size change on top.

- [ ] 3a. `pyproject.toml` — move `anthropic>=0.40,<1` and `claude-agent-sdk>=0.1.80,<1` from `[project.optional-dependencies] llm = [...]` into base `[project] dependencies`.

- [ ] 3b. `pyproject.toml` — **delete** the `[project.optional-dependencies] llm = [...]` entry entirely. No empty alias, no back-compat. `pip install a2web[llm]` should error loudly with the migration intent unambiguous.

- [ ] 3c. `uv sync --all-extras` then `du -sh .venv/lib/python3.12/site-packages/claude_agent_sdk` to confirm install size jump (~210MB expected). Record in PR description for visibility.

- [ ] 3d. `src/a2web/llm_resource.py`:
  - Drop the `try: import anthropic / except ImportError:` gate. Top-level import is now guaranteed safe.
  - Drop the `unavailable_reason = "[llm] extra not installed"` operator-hint branch in `_ensure()` or constructor.
  - The remaining "unavailable" cases: (1) no API key configured AND no Claude Code OAuth available, (2) provider misconfiguration. Both keep their existing operator hints.

- [ ] 3e. `src/a2web/routers.py` — `ask` param description: remove "Requires the `[llm]` install extra and a configured API key" → "Requires a configured API key (`ANTHROPIC_API_KEY`) or a Claude Code OAuth session".

- [ ] 3f. Audit grep `grep -rn "\[llm\]" src/ docs/` — every reference to "install the `[llm]` extra" becomes "configure `ANTHROPIC_API_KEY`". Audit `grep -rn "install_extras\|llm-extras\|optional install" src/ docs/` for any cousin phrasing.

- [ ] 3g. `tests/test_resources.py` — `test_llm_extractor_unavailable_when_extra_missing` (or similar — the test that mocks `ImportError` for anthropic import) needs adjusting:
  - The "extra not installed" branch is gone; delete tests of that path.
  - Keep / extend "no API key" tests — that's the remaining unavailable path.

- [ ] 3h. `make check` green. Install size on a fresh `uv sync` should be measurable in the PR description.

---

## Block 4 — Docs + CHANGELOG

- [ ] 4a. `CHANGELOG.md` — v0.7.0 entries:
  - Reddit search URL handler (Block 1).
  - Captcha pre-routing for `google.com/search` / `bing.com/search` → DuckDuckGo (Block 2).
  - **Breaking** — `[llm]` install extra removed. `anthropic` + `claude-agent-sdk` are now baseline deps. Install size +210MB. Migration: drop `[llm]` from your install command — `pip install a2web` is sufficient. `pip install a2web[llm]` errors loudly.

- [ ] 4b. `BACKLOG.md` — strike entries:
  - "Reddit search URLs return 403 across all tiers" (Block 1 closes this).
  - "Google Search HTML passes block detection as raw OK content" (Block 2 closes this).
  - "LLM extras require opt-in install — operator hint flow leaks install instructions to agents" (Block 3 closes this).

- [ ] 4c. `CLAUDE.md` — update if the architecture-level handler description references the old Reddit handler scope (it currently says "permalink focus, crosspost, archive escalation, short URLs" — add "search").

- [ ] 4d. `README.md` — quick-start section, if it mentions `pip install a2web[llm]` for ask functionality, update to say `--ask` works out of the box.

---

## Block 5 — Regression suite

- [ ] 5a. Curate a regression URL set in `tests/regression_urls.py` (or wherever the existing regression list lives — check during implementation). Include:
  - The Reddit search URL from feedback (`https://www.reddit.com/r/projectors/search/?q=Wanbo+Mozart+1+Pro&restrict_sr=on&sort=new`).
  - The Google search URL (`https://www.google.com/search?q=site%3Areddit.com+Wanbo+Mozart+1+Pro`) — should rewrite + succeed via DDG.
  - A live `--ask` flow against a small page — confirms LLM path works without `[llm]` install hints.

- [ ] 5b. Mark regression tests as network-required (gate behind `RUN_NETWORK_TESTS` env var) so they don't run on every `make check` but are easy to invoke manually before tagging a release.

- [ ] 5c. Document in README or a dedicated `tests/regression.md` how to run the regression suite locally and what each URL exercises.

---

## Verification

- [ ] V1. `make check` green.
- [ ] V2. MCP stdio repro: `tools/call name=fetch arguments={"url": "https://www.reddit.com/r/projectors/search/?q=projector"}` returns a structured response with a results list. Save to `/tmp/v07_reddit_search.json`.
- [ ] V3. MCP stdio repro: `tools/call name=fetch arguments={"url": "https://www.google.com/search?q=site%3Areddit.com+projector", "debug": true}` returns a response with `original_url` populated and the actual fetched URL = DDG. Save to `/tmp/v07_captcha.json`.
- [ ] V4. MCP stdio repro: `tools/call name=fetch arguments={"url": "https://example.com/", "ask": "what's on this page?"}` returns a response with `extracted_answer` populated — no operator hint about installing `[llm]`. Save to `/tmp/v07_ask_ootb.json`.
- [ ] V5. CLI cold-start time measurement (`time uvx --from . a2web web fetch --url=https://example.com/`) — confirm `Lazy[LlmExtractorResource]` keeps cold start tight (no LLM warm on a no-ask fetch). Compare against pre-migration baseline if recorded.

---

## Archive prep

- [ ] A1. Move this change to `openspec/changes/archive/2026-05-15-a2web-mcp-feature-wave/`.
- [ ] A2. If round-10 feedback (BaseSettings wire-detection + v0.38 observations) was filed alongside the migration, no action — it's its own file. Otherwise, take notes captured during this change and roll into the round-10 draft.
