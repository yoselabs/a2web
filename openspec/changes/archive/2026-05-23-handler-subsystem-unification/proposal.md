## Why

The forum/listing-extraction work just shipped surfaced three symptoms — DiscourseHandler fails on linux.do (its named default target), Discourse titles render raw HTML entities, the generic record renderer dumps a flat metadata smush — and one structural root cause: the handler subsystem was built as a parallel stack to the tier subsystem and never shared its infrastructure. Handlers run as tier 0 (first, most specific) yet have the **weakest** transport in the cascade: each of the 9 handlers hand-rolls a plain `httpx.AsyncClient` with no TLS impersonation, no proxy routing, no per-host circuit breakers, no block detection — exactly the infra `tiers/raw.py` consolidated with `curl_cffi`. Cloudflare-fronted forums (linux.do) therefore reach the handler as an anti-bot / prompt-injection banner instead of the real `.json` API. The same fragmentation produced four hand-rolled HTML-fragment strippers (one per handler), and issue 3 is the gap in copy #4. And because every handler test monkeypatches `httpx.AsyncClient.get` with a recorded JSON fixture, transport bugs are invisible to `make check` by construction — the suite can only ever be right about the rendering half of each handler.

## What Changes

Four phased threads, each landing `make check`-green:

1. **Shared fetch primitive.** Extract a `packages/http_fetch` callable from `tiers/raw.py` — `curl_cffi` Chrome impersonation, proxy routing via `ProxyPool`, per-host purgatory breakers, closed-verdict error mapping. `RawTier` and `ArchiveTier` rewire onto it (no behaviour change). All 9 handlers migrate off `httpx.AsyncClient`. Anti-bot capability becomes the default for handlers, not a thing each handler has to remember to ask for.
2. **Shared HTML-fragment converter.** Promote a `packages/html_fragment` package with one tested `to_markdown(fragment)` and `to_text(fragment)` — link-preserving (`<a href>` → `[text](href)`), entity-decoded, nbsp-folded. Replace the hand-rolled strippers in discourse / habr / v2ex / hn handlers. Every handler-rendered title and body routes through one converter; the discourse-title-class bug becomes structurally impossible.
3. **Live-contract probe.** New `make handler-probe` target outside `make check` (live network, no LLM quota): one real GET per handler against a known host, asserting `verdict == ok` end-to-end. Fixtures keep testing renderers; the probe is what tests transport. Plus a written probe-discipline convention: a finding records the *method* used (impersonation, proxy, cookies) — "the API is open" is incomplete; "open to curl_cffi Chrome-impersonated, 403 to plain httpx" is the finding.
4. **Structure-aware Record.** Carry the detector's structural decomposition through to the renderer — `Record` gains `heading_text` and `heading_link` fields (the detector already computes the latter as `primary_link`); `render_record` leads with `[heading_text](heading_link)` and renders the remaining own-scope text/links as the body. Closes the lossy detector→render boundary that makes lobste records read as `"12 rbuchberger edited 12 hours ago <comment text>..."`.

**BREAKING (internal interface only):** handler and `RawTier`/`ArchiveTier` HTTP call sites migrate off `httpx` / inline `curl_cffi` to the shared primitive. No wire / envelope change; `FetchResponse` and `AskResponse` shapes are unchanged.

## Capabilities

### New Capabilities
- `handler-transport`: shared fetch primitive used by the handler subsystem and `RawTier` / `ArchiveTier` — curl_cffi Chrome impersonation, proxy routing, per-host circuit breakers, closed-verdict error mapping, conditional-GET passthrough. One implementation, one test surface for transport.
- `handler-live-probe`: a live-network probe target (`make handler-probe`) that exercises each handler against its real host end-to-end and asserts `verdict == ok` — closes the fixture-only test blind spot that hid the linux.do failure.

### Modified Capabilities
- `site-handlers`: handlers SHALL fetch via the shared `handler-transport` primitive (no per-handler `httpx.AsyncClient`); handler-rendered titles and HTML-fragment bodies SHALL be entity-decoded and link-preserving via the shared HTML-fragment converter. The "handlers MUST NOT raise on routine HTTP failures" requirement keeps its contract — now satisfied by the primitive's closed-verdict mapping.
- `raw-tier`: `RawTier` SHALL be implemented via the shared `handler-transport` primitive (no inline `curl_cffi.AsyncSession`).
- `record-extraction`: `Record` SHALL carry the structural decomposition the detector already computes — heading text and heading link as named fields separate from body text/links — and the renderer SHALL lead with them.

## Impact

- **New packages:** `src/a2web/packages/http_fetch/` (the transport primitive) and `src/a2web/packages/html_fragment/` (the HTML-fragment converter).
- **Tier subsystem migration:** `src/a2web/tiers/raw.py` and `tiers/archive.py` switch to `http_fetch`. The conditional-GET headers, proxy handling, breaker integration move into the primitive.
- **Handler subsystem migration:** all 9 handlers (`reddit`, `hn`, `arxiv`, `github`, `wikipedia`, `twitter`, `discourse`, `habr`, `v2ex`) drop their `httpx.AsyncClient` blocks; discourse / habr / v2ex / hn drop their hand-rolled HTML strippers.
- **Record model:** `src/a2web/packages/record_extract/models.py` `Record` grows structural fields; `render.py` uses them; the detector already computes them.
- **Makefile + harness:** new `make handler-probe` target with a small Python entrypoint that walks the handler registry and probes one URL per handler.
- **No wire / envelope change.** The four forum-extraction proposals already shipped remain valid; their handlers gain anti-bot capability without changing their contracts.
- **Issue 2 is hardened as a side effect** — impersonated transport reaches the real JSON API, so the linux.do anti-AI prompt-injection banner never enters the pipeline as `content_md`.
- Closes three deferred Open Questions in `discourse-handler` / `habr-handler` / `v2ex-handler` design docs ("share the threaded/HTML renderer").
- **No new top-level dependencies.** `curl_cffi`, `httpx` (kept for non-handler call sites), `lxml` are all already pinned. The primitive is curl_cffi-only; handlers drop their `httpx` imports.
