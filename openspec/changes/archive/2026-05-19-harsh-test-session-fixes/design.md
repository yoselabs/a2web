## Context

The 2026-05-19 harsh-test session ran a2web against 9 sites spanning Reddit, HN, GitHub, arXiv (handler-served), Hepsiburada / Amazon.com.tr (SSR e-commerce, raw-tier win), Trendyol / Yandex Market (CSR e-commerce, partial or failed), NYT (paywall), TechCrunch (browser crash), X.com (anti-headless fingerprinting). The findings split into three causal buckets:

1. **Modern e-commerce ships data as JSON, not HTML.** Trendyol's product grid is `<script id="__NEXT_DATA__">`; Yandex Market dumps the entire app state as `<script type="application/json">`. Trafilatura returns navigation-menu chrome (Trendyol: 642 chars) or unparseable JSON noise (Yandex: 345k chars). Same shape as half the public web.
2. **The classifier doesn't read jina's stub vocabulary.** Jina serves a tiny markdown stub when the upstream is paywalled: `Warning: Target URL returned error 403: Forbidden`. The gate counts characters, sees ~500, calls it `length_floor`. The archive escalator only fires on `Verdict.paywall` — so NYT stays dead even though Wayback would have served it.
3. **Subprocess and lazy-load failures leak.** Camoufox's Node.js process crashed mid-render on TechCrunch (`TypeError: Cannot read properties of undefined (reading 'url')` in playwright's coreBundle.js). The Python side caught it as `connection_error` (good), but the JS stack trace went straight to the user's terminal (bad). Same shape on Trendyol: browser tier snapshots before lazy-load fires, gate sees the same nav-menu stub as raw tier, no further escalation.

These are six discrete fixes but they share enough threads (gate classifier, browser tier, packages independence) that bundling them keeps the test fixtures coherent.

Already-shipped on `main` from this session and out of scope here:
- `system_prompt=""` always-passed in `claude_code.py` (drops claude_code preset, ~50-77% cost cut, verified).
- `camoufox` moved to baseline `dependencies`, `playwright` dropped as transitive.

## Goals / Non-Goals

**Goals:**
- a2web can extract product / list data from `__NEXT_DATA__`, `__NUXT_DATA__`, `<script type="application/json">` blobs without escalating to browser tier when the JSON path suffices.
- Paywall-shaped jina stubs route to archive escalation as designed.
- Browser tier produces either a real DOM snapshot or a structured failure — never a thin success that masks a JS-rendered page.
- Subprocess noise (camoufox / playwright JS errors) lands in LDD diagnostics, not the user's terminal.
- Callers can cap content size per fetch via `--max-content-chars` CLI flag and the equivalent MCP kwarg.

**Non-Goals:**
- Bypassing anti-headless fingerprinting (X.com, Instagram, TikTok). These remain out of scope; the answer there is authenticated APIs + the existing cookie-jar.
- Generic JavaScript execution / interaction beyond scroll-to-bottom (no click sequences, no form-fill).
- Re-architecting the gate classifier. The fixes here are additive rules on the existing classifier, not a new gate.
- Localization fixes for the extraction template ("1.3 bin" → "1300"). Cosmetic, would need to perturb the byte-identical WebFetch template — separate concern.

## Decisions

### 1. JSON extractor lives in `packages/content_extract/json_in_script.py`

Pure boundary function: `extract_json_payloads(html: str) -> list[JsonPayload]` where `JsonPayload` is a package-owned dataclass (`source: Literal["next_data", "nuxt_data", "ld_json", "generic"]`, `data: dict | list`, `script_id: str | None`). The a2web seam converts JSON to a synthetic markdown table via a domain-side adapter (`src/a2web/domain.py::json_to_markdown_rows`).

**Alternatives considered:**
- Run JSON extraction *inside* trafilatura via a custom callback — rejected, trafilatura is a black box we don't want to fork.
- Build a new tier `json` between `raw` and `jina` — rejected, the JSON is *already* in the raw response; this is an extraction-stage concern, not a fetch-tier one.

### 2. JSON extraction runs in the existing `_phase_extract` between trafilatura and length-check

Flow: raw response → trafilatura → if extracted markdown is thin (<2KB) OR contains <3 sentences, try JSON extractors → if any returns a payload with product/list shape, convert to markdown table and replace the trafilatura output. Length check runs against the post-replacement markdown.

**Why post-trafilatura, not pre:** trafilatura is fast (~50ms) and on SSR pages it produces a richer result than JSON shovelling. Only pay the JSON path when trafilatura comes back thin.

**Detection shapes (`<script>` selectors):**
- `script#__NEXT_DATA__[type="application/json"]` — Next.js (Trendyol, Hepsiburada premium, half of e-commerce).
- `script#__NUXT_DATA__` — Nuxt.
- `script[type="application/ld+json"]` — Schema.org JSON-LD (most product pages — gives `Product` + `Offer` + `AggregateRating` directly).
- `script[type="application/json"][data-*]` — generic app-state (Yandex Market, custom React shells).

JSON-LD is preferred when present: it's a stable schema, parseable to a clean table without app-state navigation.

### 3. Paywall classifier: jina-stub recognition by string match

In the gate classifier, when `tier == "jina"` *and* content_md contains either `Target URL returned error 401` or `Target URL returned error 403` *and* the body is <2KB, emit `Verdict.paywall`. Trigger keyed off the literal jina warning strings — these are stable across jina's lifetime and unique to its error stubs.

**Alternative considered:** Inspect jina's HTTP status code from the upstream proxy chain — rejected, jina returns 200 even when upstream is 403; the only signal is the in-body warning text.

### 4. Thin-browser-response: per-host heuristic, not global

A global "browser response <1KB = fail" rule would mis-fire on intentionally minimal landing pages. Instead: maintain a small `JS_HEAVY_HOSTS` set (initially: `x.com`, `twitter.com`, `instagram.com`, `tiktok.com`, `trendyol.com`, `aliexpress.com`, plus any host where the *raw tier already returned <1KB* — known-CSR-shape). On browser-tier 200 OK with <1024 chars AND host in set, downgrade to `length_floor` so escalation continues.

**Alternative considered:** Detect via DOM heuristics (count of `<script>` tags, presence of root mount node like `<div id="root">`). Rejected as fragile — false positives on legitimate landing pages.

### 5. Browser tier: scroll-then-wait, only when thin

Modifying every browser fetch to scroll-to-bottom adds ~2s × every escalation. Instead: after the initial `networkidle` snapshot, check `len(html) < 4096` → if thin, scroll to bottom (Playwright's `evaluate('window.scrollTo(0, document.body.scrollHeight)')`) → `wait_for_load_state('networkidle')` again with a 2s cap → re-snapshot. Bounded retry, no infinite scroll loop.

### 6. Camoufox stderr capture: subprocess redirect

In `BrowserPool._ensure()`, after launching camoufox, monkey-patch `sys.stderr` for the playwright subprocess via the `env` or `stderr=` kwarg on the subprocess.Popen call camoufox uses internally. If camoufox doesn't expose that, wrap the `AsyncCamoufox()` construction with a stderr-redirect context manager (`contextlib.redirect_stderr` won't catch subprocess output — need `os.dup2` on file descriptor 2, OR run camoufox under a stderr-capturing wrapper).

**Spike likely required:** the exact mechanism depends on whether camoufox/playwright's Node child process inherits stderr from the Python parent or pipes it. First task = 1h spike to find the working knob; if it's blocked, fall back to documenting that browser-tier stderr leaks and routing users to redirect at the shell level.

### 7. `--max-content-chars` plumbing

Add an `Annotated[int | None, pydantic.Field(...)]` param to both `fetch` (ask) and `fetch_raw` in `routers.py`. Plumb through `fetcher.fetch()` → `FetchContext.max_content_chars` → `LlmExtractorResource.extract()` → `Extractor.__init__`'s `max_content_chars` (which already exists but isn't reachable from outside the resource builder). On `None` the existing default (100_000) stays.

## Risks / Trade-offs

- **JSON extractor produces hallucinated structure:** if app-state JSON is sprawling (Yandex's 345k blob), naive `json_to_markdown_rows` could synthesize fake-looking tables that the model treats as ground truth. → Mitigation: only convert *known* shapes (JSON-LD `Product`, Next.js `pageProps.products`, etc.). Unknown shapes → don't synthesize; fall back to the existing trafilatura output.
- **Paywall string-match brittleness:** jina could rephrase its warning string in a future deploy. → Mitigation: anchor on `error 40[13]` substring (regex) not full match; add a contract test against a snapshotted jina stub fixture.
- **Thin-browser host list rots:** new JS-heavy sites pop up daily. → Mitigation: ship with a small seed list (the 6 we know break) + log every thin-browser response with host so the list grows from real signal.
- **Scroll changes timing on every browser fetch:** even bounded by "only when thin", the extra check + potential 2s wait adds tail latency. → Mitigation: emit `StageStarted/Ended("browser_scroll_retry")` LDD event so we can measure how often it fires in real traffic.
- **Stderr capture might require subprocess wrapping that breaks under uv tool install:** the file-descriptor redirect path uses `os.dup2` which behaves differently inside `uv tool` venvs. → Mitigation: 1h spike to confirm mechanism before committing to the approach; have the "document + shell-level workaround" exit hatch ready.
- **`--max-content-chars` lets agents footgun themselves:** a caller sets it to 1000 and then asks a complex extraction question — gets garbage and blames a2web. → Mitigation: documented default stays at 100_000; CLI help text explicitly warns that lower values trade quality for cost.

## Migration Plan

No data migration. All changes are additive at the API surface:
- New CLI flag defaults to `None` (= keep existing behavior).
- New JSON path runs only when trafilatura returns thin output (no change for SSR sites).
- Paywall classifier is a new rule in an existing classifier — only matches jina-stub responses that today silently fail.
- Thin-browser heuristic only fires on the seed JS-heavy host set.
- Stderr capture is transparent to callers.

Rollout is in-place. No deprecations, no breaking changes. Single PR → bench re-run against the same 8 harsh-test fixtures to confirm Trendyol passes and NYT escalates to archive.

## Open Questions

1. **JSON-LD selection priority** — when a page has *both* `__NEXT_DATA__` and `application/ld+json`, which wins? Lean toward JSON-LD (stable schema) but Next.js often has richer product data. Probably: try JSON-LD first, fall back to `__NEXT_DATA__` if LD result is sparse (<3 fields).
2. **Camoufox stderr knob exists?** Need spike before implementation. If not, we ship 5 of the 6 fixes plus a documented limitation.
3. **Should `--max-content-chars` cap the *fetched* body or the *extracted* markdown?** Today's `max_content_chars=100_000` is on the markdown going into the LLM prompt. Naming would suggest fetched body, semantics are extracted markdown. Probably keep semantics, rename to `--max-extract-chars` to remove ambiguity.
