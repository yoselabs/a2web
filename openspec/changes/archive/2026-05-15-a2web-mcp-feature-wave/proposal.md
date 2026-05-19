# a2web MCP feature wave (post-v0.38-migration)

## Why

Three features were held back during the v0.32→v0.38 a2kit migration period because the MCP transport was broken — there was no point shipping MCP-facing surface area into a transport that returned `"Error calling tool 'fetch'"` on every call. With the migration landing (sibling change `2026-05-15-a2kit-v038-migration`), the MCP path is structurally sound and these features can ship.

| Feature | Why now | Why bundled here |
|---|---|---|
| **Reddit search URL handler** | Highest-value research endpoint that's currently 100% fail (raw 403, jina 403, archive miss). POC-verified `/r/<sub>/search.json?q=...` with Safari UA returns 25 valid post stubs (151KB on test query). | Reddit handler already shipped; this is a regex + render extension. |
| **LLM extras promoted to core** | The `--ask`/`ask=` path is the single biggest context-cost lever for agent callers. With `[llm]` as an opt-in extra, the operator-hint flow ("install the [llm] extra") makes a2web lose to WebFetch on summarization-friendly pages even where a2web wins on access. User confirmed bundling `claude-agent-sdk` (~210MB) is the right call — most a2web callers run inside Claude Code and rely on the OAuth piggyback. | One packaging change; co-shipped with the Lazy[LlmExtractorResource] tool surface from the migration so the user-visible "ask works out of the box" story lands together. |
| **Captcha-redirect pre-routing for search engines** | Google Search returns a captcha page that passes our length floor and doesn't match block-detector patterns — falls through as "raw ok" with content that's a captcha redirect. Bing has the same shape. Pre-route to DDG / Brave; the captcha hosts are never useful for raw scraping. | Pure playbook addition (URL rewrite + known-host registry). Co-ships with Reddit handler because both are "research-flow URL handling" work. |

All three were sketched in `A2KIT_FEEDBACK_v0.32-mcp.md` § "What we'd ship in a2web once round-8 lands" but blocked on the migration. The migration now ships them as feature follow-ups.

Deferred (not in this change):
- `@a2kit.read(timeout="60s")` adoption — a2web's tiers manage their own timeouts via `asyncio.wait_for`; switching is cosmetic. Defer to a focused "adopt-v0.38-affordances" change if it ever becomes worthwhile.
- TestClient-driven integration tests — net-new test surface, not feature work. Defer.
- a2web BaseSettings wire-detection workaround review — the migration's explicit `app.provide(get_settings)` is fine; revisit only after a2kit fixes its `wire_input_params` to also check `_looks_like_basesettings` (round-10 ask).

## What Changes

### Reddit search URL handler

**`src/a2web/handlers/reddit.py`**

- Extend the matcher: handler.`matches(url)` returns True for Reddit `/r/<sub>/search/`, `/search/`, and the unscoped variants in addition to today's `/r/<sub>/comments/...`. New regex pattern alongside the existing `_COMMENTS_PATH_RE`.
- URL rewrite: `_to_json_url(url)` already strips trailing `/` and appends `.json` — verified working against `/r/projectors/search/?q=...` → `/r/projectors/search.json?q=...` (the existing trailing-`/` → `.json` rewrite path applies unchanged).
- New rendering branch: `_render_search(payload)` consumes the `Listing` response shape (single Listing of `t3` post stubs, NOT the `[post, comments]` pair shape that `_render_thread` expects). Output is a markdown list of results, each entry containing `r/<sub> | title | score | num_comments | permalink | created_utc`. Cap at 25 entries by default (Reddit's natural page size).
- `_render_thread` is unchanged. Handler dispatches to `_render_search` based on the URL shape detected at `matches()` time (carry the shape forward through the handler entry).
- Returns `TierResult` with `pre_rendered: Rendered` (matching the existing handler contract — orchestrator skips trafilatura + metadata when `pre_rendered` is set). Sets `verdict=Verdict.ok` on non-empty results.
- Empty / zero-results case: returns `TierResult(no_match=True)` so orchestrator falls through to other tiers (raw / jina won't help for search either, but consistency wins).
- Errors (403, 429, ≥400): same translation table as existing comments handler — `rate_limited`, `forbidden`, `connection_error`. No archive escalation for search URLs (Wayback doesn't have useful captures of dynamic search pages).

**`tests/test_handlers.py`** — add Reddit search cases:
- `r/projectors/search/?q=Wanbo+Mozart+1+Pro&restrict_sr=on&sort=new` → returns ≥10 results, each with title + permalink.
- `r/<bogus_sub>/search/?q=nothing-matches-here` → returns `no_match=True` or empty list cleanly.
- Subreddit-scoped vs unscoped (`/search/?q=...` without `r/<sub>`) — verify both shapes match.

### LLM extras promoted to core

**`pyproject.toml`**

- Move `anthropic>=0.40,<1` and `claude-agent-sdk>=0.1.80,<1` from `[project.optional-dependencies] llm = [...]` to base `[project] dependencies`. Install size jumps from ~30MB to ~240MB (claude-agent-sdk bundles ~210MB Claude Code binary in `_bundled/`).
- **Delete** the `[project.optional-dependencies] llm` entry entirely. No empty alias, no back-compat shim. `pip install a2web[llm]` errors loudly — migration intent unambiguous, matches a2web project convention.
- Update keywords list if needed (currently includes "llm").

**`src/a2web/llm_resource.py`**

- Drop the `try: import anthropic / except ImportError:` gate around construction. The dep is now guaranteed.
- Drop the `unavailable_reason = "[llm] extra not installed"` operator-hint path. The remaining unavailable case is "no API key configured" — that operator hint stays.
- `LlmExtractorResource._ensure()` opens the configured provider eagerly (no more conditional based on dep presence).

**`src/a2web/routers.py`**

- Update the `ask` param description: drop "Requires the `[llm]` install extra" — the dep is now baseline. Keep "and a configured API key" — that's still optional configuration.

**Operator hints** (audit grep for "install" + "[llm]" across the codebase) — remove install-the-extra hints. The remaining hints become:
- No API key + no Claude Code OAuth → "Configure `ANTHROPIC_API_KEY` or run inside Claude Code".
- Provider misconfig → existing path.

**`tests/test_resources.py`** — adjust the `ImportError`-gated tests for `unavailable_reason`. The "extra not installed" branch dies; keep tests for the "no API key" branch.

### Captcha-redirect pre-routing for search engines

**`src/a2web/domain.py`** (or new `src/a2web/captcha_routing.py` — pick by line-count after step 1)

- New pure function `rewrite_captcha_host(url: str) -> str | None`. Returns a rewritten URL when the input host is a known captcha-emitter (`google.com/search`, `www.google.com/search`, `bing.com/search`, `www.bing.com/search`), `None` otherwise.
- Rewrite target by default: `https://duckduckgo.com/html/?q=<urlencoded-query>`. Preserves the `q` parameter; drops everything else (Google's `tbm`, `start`, etc. don't map cleanly).
- Known-host registry is a module-level frozenset — operationally lookup-only, not user-configurable in v0.7. (If a user wants Brave / Kagi as the rewrite target, that's a settings addition for a later change.)

**`src/a2web/fetcher.py`** — orchestrator entry rewrite step

- Add a step at the top of `orchestrate(...)` before tier dispatch: if `rewrite_captcha_host(url)` returns a rewritten URL, emit a `StageStarted("url_rewrite_captcha")` LDD event, swap the URL, increment the `url_rewrites` counter on FetchContext, emit `StageEnded`, and proceed with the rewritten URL. The original URL is preserved on FetchContext as `original_url` for diagnostics.
- The block-detector gate (`packages/block_detector.py`) gains a Google-captcha pattern detector as a **second-line defense** — if a URL slips past the pre-route (e.g. user passed a Google URL via redirect we didn't recognize), the gate detects captcha-page markers (`/sorry/index`, "Our systems have detected unusual traffic") and emits a `Verdict.block_page_detected` with `operator_hint(code="captcha_redirect", message="Search engine captcha; consider DDG/Brave directly")`.
- Counter cap: `url_rewrites` per fetch is already bounded by the playbook to 2; this rewrite respects the same cap (defense against rewrite loops — DDG doesn't redirect anywhere problematic, but the constraint is structural).

**`tests/test_fetcher.py`** — add cases:
- `https://www.google.com/search?q=site%3Areddit.com+Wanbo+Mozart+1+Pro` → rewritten to DDG URL before tier dispatch; FetchContext shows `original_url = google...` and final URL = DDG.
- `https://www.bing.com/search?q=...` → same shape.
- Real fetch via DDG returns useful results (live test gated by `RUN_NETWORK_TESTS` env var — same convention as existing live-only tests).

### `CHANGELOG.md`

Add v0.7.0 "MCP feature wave" entries:
- Reddit search URL handler.
- `[llm]` install extra retired — `anthropic` + `claude-agent-sdk` now baseline deps. Install size +210MB.
- Captcha pre-routing for `google.com/search` / `bing.com/search` → DuckDuckGo.

### `BACKLOG.md`

- Strike or remove any entries referencing "Reddit search broken", "LLM extras require opt-in install", "Captcha redirect not detected".

## Out of scope (for this change)

- Brave / Kagi / other search engines as captcha rewrite targets (settings expansion).
- TestClient-driven integration tests over MCP stdio (separate change — value, but not feature work).
- `@a2kit.read(timeout="60s")` adoption.
- Reddit `more`-stub expansion (large-thread comment coverage) — separate change once a real repro case exists; the threads cited in original feedback turned out to have 1 and 27 comments respectively, no truncation observed.

## Dependencies

This change **requires** `2026-05-15-a2kit-v038-migration` to land first:
- Reddit search handler: no migration dep, but ships into the unblocked MCP transport so it's user-visible.
- LLM-OOTB: co-ships with the migration's `Lazy[LlmExtractorResource]` tool signature — the user-facing story is "ask now works out of the box, gated cleanly via Lazy".
- Captcha routing: no migration dep, same MCP-visibility reasoning.

If the migration slips, this change can ship Reddit search and captcha routing standalone (both are CLI-functional today). LLM-OOTB also ships standalone but loses the Lazy cold-start angle.
