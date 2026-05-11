# v0.3 — engine improvements: tasks

## 1. Envelope diet

- [ ] 1.1 Stop populating `fit_md` with a copy of `content_md` in `src/a2web/fetcher.py`. Leave `fit_md=None` when no pruning filter ran.
- [ ] 1.2 Update `src/a2web/models.py` if needed so `fit_md: str | None = None` is the only valid shape (already is per CLAUDE.md; verify and document).
- [ ] 1.3 Add `include_links: bool = False` param to the `fetch` tool in `src/a2web/routers.py` (via `Annotated[bool, a2kit.Param(description=...)]`).
- [ ] 1.4 Wire the param through `FetchContext` so `fetcher.py` knows whether to populate `FetchResponse.links`. When `False`, return `links=[]`.
- [ ] 1.5 Add `debug: bool = False` param to the same tool.
- [ ] 1.6 Add `FetchResponse.diagnostics_summary: str` field — always populated with a one-line `tier=<x> verdict=<v> total_ms=<n>` string.
- [ ] 1.7 When `debug=False`, exclude the full `diagnostics` list from serialization (omit, don't null). Pydantic's `model_dump(exclude={...})` at the boundary.
- [ ] 1.8 BDD scenario: caller with `include_links=False` (default) sees empty links list; caller with `include_links=True` sees the full list.
- [ ] 1.9 BDD scenario: caller with `debug=False` (default) sees no `diagnostics` key in JSON, but `diagnostics_summary` is populated; caller with `debug=True` sees both.
- [ ] 1.10 Update CHANGELOG.md: "links/diagnostics now opt-in. Default response shape ~80% smaller. Pass `include_links=True` to restore previous behavior."

## 2. Reach reliability: gate escalation

- [ ] 2.1 Add JS-shell detection to `src/a2web/gate/block_detector.py`. When `verdict == length_floor` AND raw body contains a JS-framework marker (Next.js / React / Vue root, or `<noscript>` shell), set `suggested_tier = "browser"`.
- [ ] 2.2 Confirm `src/a2web/fetcher.py` orchestrator already dispatches browser on `suggested_tier == "browser"`. (Existing browser-tier spec says yes; verify.)
- [ ] 2.3 BDD scenario: JS-shell page with thin extracted text triggers `suggested_tier="browser"`; orchestrator dispatches browser tier; final `from_browser=True` in `meta`.
- [ ] 2.4 BDD scenario: thin page with NO JS-framework markers keeps `suggested_tier=None` (no spurious browser cost).

## 3. Reach reliability: Linear false-positive

- [ ] 3.1 Capture the Linear payload from the benchmark as a test fixture in `tests/fixtures/linear-marketing/`.
- [ ] 3.2 Reproduce the FP in a unit test against `block_detector` and / or `fetcher.py`.
- [ ] 3.3 Identify whether the defect is (a) over-aggressive length threshold in `block_detector` or (b) verdict→status mapping in `fetcher.py`. Document root cause in the test.
- [ ] 3.4 Fix the identified component; status=ok on Linear.
- [ ] 3.5 BDD scenario: compact SPA landing pages with real content return `status=ok`, not `status=failed`.

## 4. Reddit handler: old.reddit fallback

- [ ] 4.1 In `src/a2web/handlers/reddit.py`, when the `.json` request returns 404 OR HTTP 200 with an empty `data.children`, attempt a second GET against `old.reddit.com` + the same path.
- [ ] 4.2 Parse the old.reddit HTML via trafilatura (it's server-rendered).
- [ ] 4.3 Map response into `Rendered` the same way the JSON path does (title, byline, content_md, headings).
- [ ] 4.4 BDD scenario: thread URL where `.json` returns 404 → old.reddit fallback returns full content.
- [ ] 4.5 BDD scenario: thread URL where `.json` succeeds → old.reddit path is NOT touched (no extra request).
- [ ] 4.6 Verify the existing failed-thread test from `benchmarks/vs-webfetch/2026-05-11/runs/reddit-thread/` becomes a passing one after this change.

## 5. Twitter / X handler via Nitter

- [ ] 5.1 New file `src/a2web/handlers/twitter.py`. Match `x.com`, `twitter.com`, `www.x.com`, `www.twitter.com` + path `/<user>/status/<id>(/.*)?`.
- [ ] 5.2 Add `nitter_instances: list[str] = []` to `AppSettings` (env `A2WEB_NITTER_INSTANCES`, comma-separated, also from YAML config).
- [ ] 5.3 Add a small rotation helper — random shuffle per fetch, per-instance circuit breaker via existing `purgatory` infra.
- [ ] 5.4 For each instance in rotation order, try `GET <instance>/<user>/status/<id>` with a 5s timeout. First success returns. All-fail → `TierResult(no_match=True)`.
- [ ] 5.5 Parse via trafilatura. Tweet body → `content_md`; replies → headings or appended sections.
- [ ] 5.6 Register the handler in `src/a2web/handlers/__init__.py`.
- [ ] 5.7 BDD scenario: when `nitter_instances` is empty, handler matches=False (returns no-match silently; never errors).
- [ ] 5.8 BDD scenario: with one working instance configured, fetch returns content (mocked Nitter HTML).
- [ ] 5.9 BDD scenario: when first instance times out, rotation falls through to next.

## 6. Anticipatory v0.4 prep

- [ ] 6.1 In `benchmarks/vs-webfetch/2026-05-11/judge.py`, extract the judge + reader prompt strings into a sibling `prompts.py`.
- [ ] 6.2 Extract the `claude_p` subprocess function into a `provider.py` with a `class ClaudeCliProvider`. Keep behavior identical.
- [ ] 6.3 No new top-level imports; no new files outside `benchmarks/`.

## 7. Verification

- [ ] 7.1 `make check` clean (lint + ty + tests ≥85% coverage).
- [ ] 7.2 Re-run `benchmarks/vs-webfetch/2026-05-11/runner.py` against the same corpus; produce a v0.3 results.tsv beside the v0.2 one for direct comparison.
- [ ] 7.3 Confirm: total a2web tokens across corpus drops by ≥70%. Confirm: 2 / 20 URLs flipped from `status=failed` to `status=ok` (Linear + Reddit).
- [ ] 7.4 Update CHANGELOG.md with the before/after benchmark numbers.
- [ ] 7.5 Update BACKLOG.md: remove items now shipped; mark Reddit OAuth as deferred-but-tracked.
