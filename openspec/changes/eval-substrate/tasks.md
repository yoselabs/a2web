## 1. Cassette format + corpus layout

- [ ] 1.1 Define the on-disk case layout under `eval/corpus/<corpus>/<case>/` — `case.yaml`, `inputs/`, `baseline/`, `meta.yaml` — and a loader that reads it (extending the existing `eval/corpus.yaml` entry shape: slug/url/class/task/needs/criteria/next_links_expected).
- [ ] 1.2 Define the raw cassette unit: serialize/deserialize a `http_fetch.FetchOutcome` (body, content_type, status_code, final_url, headers, verdict, conditional_hit) to/from `inputs/raw.http` in plain readable form.
- [ ] 1.3 Define the failure-class taxonomy (A clean-schema / B source-omits-or-JS-or-walled / C schema-lies) as the `class` field on `case.yaml`; document A/B/C/JS in a corpus README.
- [ ] 1.4 Decide the harness module home (replay/assert side under `tests/`, capture dev script under a non-packaged `eval/_capture/`) and stub the directories; assert `eval` capture code is not importable from `a2web.*`.

## 2. Raw-tier replay (MVP)

- [ ] 2.1 Implement the centralized `fetch_bytes` replay fixture (one pytest fixture pointing the chokepoint at the cassette reader; loud structured failure with the `make eval-refresh` hint on a cassette miss).
- [ ] 2.2 Implement `make eval-capture URL=… Q=… CORPUS=… ID=…` — run the real in-process app live, tee every `fetch_bytes` egress into `inputs/`, record the produced answer + contract into `baseline/`, write `meta.yaml`.
- [ ] 2.3 Implement `make eval-replay CORPUS=…` deterministic replay over a corpus using `a2kit.testing.client`.
- [ ] 2.4 Seed the Hepsiburada listing case into a new `regression` corpus via capture; commit the cassette + blessed baseline.
- [ ] 2.5 Write the deterministic contract test (`tests/…`) that replays the `regression` corpus and asserts `contract.json` (field presence, token bound, tier path); confirm it is collected by `make check` (which runs `test-cov`).

## 3. Browser-tier capture + override

- [ ] 3.1 Implement `CassetteBrowserPool` and wire it via `client.override(BrowserPool, …)` so the browser tier is served the frozen `inputs/rendered.html`; never launch Camoufox at replay time.
- [ ] 3.2 Implement the eager-capture policy: always freeze raw; eagerly freeze rendered DOM for `commerce`/`js`/`spa`-tagged cases; on-use otherwise; `--all-tiers` capture flag forces eager-everywhere.
- [ ] 3.3 Implement and test the loud-gap behavior: a replayed case that escalates to a tier with no frozen entry fails with a structured message (case id + tier + refresh command) and makes no live call.

## 4. LLM-as-egress recording

- [ ] 4.1 Implement `CassetteLlm` and wire it via `client.override(LlmExtractorResource, …)` to serve a recorded provider response from `inputs/llm/*.json`.
- [ ] 4.2 Decide and document the LLM-recording key (prompt-hash vs (url, tier)) so it coexists with the `EXTRACT_*` cache prefix without leaking per-page variation into the cached prefix (coordinate with change `multi-source-extraction-input`).
- [ ] 4.3 Extend the deterministic contract test to assert byte-exact answer + exact token cost under full LLM replay.

## 5. Breaking corpus + refresh/bless

- [ ] 5.1 Add `breaking` corpus cases spanning class A, B, and C (each declaring its class); capture cassettes + baselines.
- [ ] 5.2 Implement `make eval-refresh CASE=…` — re-capture `inputs/`, re-run replay, print a diff of the new answer vs blessed `baseline/`; never overwrite without bless.
- [ ] 5.3 Implement the `A2WEB_BLESS_EVAL=1` re-bless path (mirroring the existing `A2WEB_BLESS_CONTRACTS=1` / `make bless` idiom).

## 6. Bench split + judge pinning

- [ ] 6.1 Split the existing `make bench` (`python -m a2web.llm_eval`) lane so LLM-judged axes (answer quality, clarity, next_links) stay live/informational and do not gate `make check`.
- [ ] 6.2 Pin and record the judge model id in the `make bench` run report.

## 7. Validate the instrument + wrap

- [ ] 7.1 Prove the substrate works end-to-end: replay the Hepsiburada regression case deterministically twice and confirm byte-identical answer/tier/token output.
- [ ] 7.2 Update `docs/architecture/extraction-fidelity-program.md` Status: `eval-substrate` landed; record it as the precondition that unblocks confirming ADR-0004–0007.
- [ ] 7.3 Update `CHANGELOG.md` and the `test-layout` / `output-benchmark` capability docs to reflect the corpus/replay homes and the make-check vs make-bench rule.
- [ ] 7.4 Run `make check` green (lint + ty + test-cov + arch).
