## 1. Phase 1 — Shared fetch primitive + tier / handler migration

- [x] 1.1 New `src/a2web/packages/http_fetch/` — `__init__.py` re-exporting the public surface; `models.py` with `FetchOutcome` dataclass (`body, content_type, status_code, final_url, headers, verdict, conditional_hit`); `fetch.py` with `async def fetch_bytes(url, *, headers, timeout_s, proxy_url=None, cookies=None, conditional_extras=None, breaker=None) -> FetchOutcome`. Pure infra — no `a2web.<domain>` imports; `Verdict` enum lives in `models.py` already at the top of the package (or import from `a2web.models` per the package contract — confirm against `tests/test_packages_independence.py`).
- [x] 1.2 Implement the primitive — curl_cffi `AsyncSession` per call with `impersonate=<project default>`, header passthrough, timeout, `proxy_url` → `proxies={...}`, optional `breaker` via `async with breaker`, `conditional_extras` → `If-None-Match` / `If-Modified-Since`, exception → closed-`Verdict` mapping (timeout, connection error, proxy error). Returns `FetchOutcome` — never raises on routine failures. Cookie / auth values MUST NOT appear in any diagnostic output.
- [x] 1.3 Capability tests for `http_fetch` — impersonation flag plumbed; 404/429/5xx → closed verdicts; timeout → `Verdict.timeout`; `proxy_url` plumbed and proxy error → `Verdict.proxy_unavailable`; breaker-open short-circuits without a network call; `conditional_extras={"etag": "..."}` + 304 → `verdict==ok, conditional_hit==True, body==b""`; cookies forwarded; no cookie value in stringified diagnostics.
- [x] 1.4 Migrate `tiers/raw.py` — body shrinks to: build headers (with conditional-extras), acquire host breaker, `await fetch_bytes(...)`, apply raw's HTML-tier content-type policy (`"html" not in content_type → content_type_mismatch`), wrap in `TierResult`. Drop `from curl_cffi import requests as curl_requests` and the inline `AsyncSession` block. Behaviour-identical to today.
- [x] 1.5 Migrate `tiers/archive.py` — same shape: replace its inline curl_cffi calls with `fetch_bytes`. The hedged Wayback / archive.ph anyio task group keeps its control flow; each branch now calls the primitive.
- [x] 1.6 Migrate the 9 handlers (`reddit`, `hn`, `arxiv`, `github`, `wikipedia`, `twitter`, `discourse`, `habr`, `v2ex`) — drop every `httpx.AsyncClient(...)` construction; replace each `await client.get(url, ...)` with `await fetch_bytes(url, headers=..., timeout_s=..., cookies=..., breaker=...)`. Preserve handler-side control flow (reddit's `.json` → old.reddit → archive-signal; habr/v2ex/discourse's anyio task-group parallel fetches). Remove `import httpx` from each handler.
- [x] 1.7 Update handler tests — every `monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)` becomes `monkeypatch.setattr("a2web.packages.http_fetch.fetch_bytes", _fake_fetch_bytes)` (or equivalent seam). Existing recorded JSON fixtures stay unchanged; the seam name moves.
- [x] 1.8 Confirm `tests/architecture/test_packages_independence.py` passes — the `http_fetch/` folder has zero `a2web.<domain>` imports.
- [x] 1.9 `make check` green for Phase 1 — lint, `ty`, full suite, coverage ≥ 85%.

## 2. Phase 2 — Shared HTML-fragment converter + handler render cleanup

- [x] 2.1 New `src/a2web/packages/html_fragment/` — `__init__.py` exporting `to_markdown(html, *, base_url=None) -> str` and `to_text(html) -> str`. lxml-backed (`lxml.html.fragment_fromstring` / `fromstring` with the html parser); link-preserving (`<a href>` → `[text](href)`); entity-decoded; `\xa0` → space; empty input → `""`; `to_markdown` makes hrefs absolute when `base_url` given. No `a2web.<domain>` imports.
- [x] 2.2 Capability tests for `html_fragment` — entity decode (`&rsquo;` → `'`); link preserve; nbsp fold; nested tags (`<p><strong>x</strong> <a>y</a></p>`); malformed HTML survives (no raise); `base_url` absolutizes; empty input.
- [x] 2.3 Replace `discourse._cooked_to_md` → `html_fragment.to_markdown`; replace `discourse._render_topic` title handling → `html_fragment.to_text(payload["fancy_title"])`. Drop the file-local `_cooked_to_md`.
- [x] 2.4 Replace `habr._html_to_md` + `_text_of` → shared converter; drop both.
- [x] 2.5 Replace `v2ex._html_to_md` → shared converter; drop it.
- [x] 2.6 Replace `hn._strip_html` → shared converter (`to_markdown` for the item / comment HTML); drop it.
- [x] 2.7 New tests — `test_handlers_discourse.py` asserts `pre_rendered.title` contains no `&` entity for a `fancy_title` carrying `&rsquo;`; one analogous title-decode test per handler that renders an HTML title.
- [x] 2.8 `make check` green for Phase 2 — lint, `ty`, full suite, coverage ≥ 85%.

## 3. Phase 3 — Live-contract probe

- [x] 3.1 New `scripts/handler_probe.py` (or `src/a2web/handler_probe.py`) — async entrypoint that walks `a2web.handlers._HANDLERS`, picks the representative URL for each from a checked-in `_PROBE_URLS` map, builds an `AppState` via the in-tree DI / test seam, awaits `handler.fetch(url, state=state)`, asserts `verdict == Verdict.ok` AND `pre_rendered.content_md` non-empty. Exits non-zero on any failure.
- [x] 3.2 `_PROBE_URLS` map — one representative URL per handler. Initial set: a Reddit comment thread, an HN item, an arXiv abs page, a Wikipedia article, a GitHub repo, a Twitter status (when `nitter_instances` configured), a Discourse topic on `linux.do`, a Habr article, a V2EX topic. Missing entry for a registered handler MUST fail loudly.
- [x] 3.3 `make handler-probe` target in `Makefile` — `uv run python -m a2web.handler_probe` (or the script path). NOT wired into `make check`.
- [x] 3.4 Probe-discipline note — short paragraph in `src/a2web/handlers/README.md` (or `docs/`) saying: when adding a handler, the probe finding MUST name the transport method (`curl_cffi-impersonated`, `with-cookies`, etc.); the implementation MUST call `fetch_bytes` (or stronger). Linked from the `handler-live-probe` requirement.
- [x] 3.5 Run `make handler-probe` against the current registry — MUST pass for `linux.do` (the named target the just-shipped DiscourseHandler currently fails on); the green probe is the closing assertion that phases 1 + 2 fixed the structural gap.

## 4. Phase 4 — Structure-aware Record

- [x] 4.1 `packages/record_extract/models.py` — `Record` gains `heading_text: str | None`; rename `primary_link` → `heading_link`. Boundary type, no other callers besides the package + `fetcher._records_to_next_links`.
- [x] 4.2 `packages/record_extract/detector.py` — populate both fields. `_heading_link` already finds the heading element's first anchor; expose its `_collapse(_own_text(heading_el, sig))` as `heading_text`. Both populated together; fall through to `None` when no heading.
- [x] 4.3 `packages/record_extract/render.py` — `render_record` signature gains `heading_text` + `heading_link` (or takes a `Record`); first line is `[heading_text](heading_link)` (or `heading_text` if no link); body line strips `heading_text` from the leading own-text smush; remaining links render as before. Depth indent unchanged.
- [x] 4.4 `fetcher._records_to_next_links` — `record.primary_link` → `record.heading_link` rename. Source candidates still come from `heading_link`.
- [x] 4.5 Update `tests/capabilities/record_extraction/test_record_extract.py` — assert each record's `markdown` first line is `- [heading_text](heading_link)`; assert the heading text does NOT also appear in the body line; rename `primary_link` → `heading_link` in assertions.
- [x] 4.6 Update `tests/capabilities/extraction/test_extraction_ladder.py` aggregator-record-emits-source-and-discussion test if any assertion names `primary_link`.
- [x] 4.7 `make check` green for Phase 4 — lint, `ty`, full suite, coverage ≥ 85%.

## 5. Verify

- [x] 5.1 Re-run `make handler-probe` after all phases — green; specifically `linux.do` succeeds.
- [x] 5.2 Re-run `make bench` (live-network, spends LLM quota — user-gated); confirm lobste records now read as `[title](url)\n  meta` not the flat smush, and no article regression. Record findings in `eval/findings_<date>.md` as a follow-up run.
