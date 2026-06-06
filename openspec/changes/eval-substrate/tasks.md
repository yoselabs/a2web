## 1. Cassette format + corpus layout

- [x] 1.1 Define the on-disk case layout under `eval/corpus/<corpus>/<case>/` — `case.yaml`, `inputs/`, `baseline/`, `meta.yaml` — and a loader that reads it (`eval/_capture/corpus.py`, extending the bench entry shape with `question`/`failure_class`/`tags`).
- [x] 1.2 Define the raw cassette unit: serialize/deserialize a `http_fetch.FetchOutcome` to/from `*.http` in plain readable form (`eval/_capture/cassette.py`; UTF-8 body for diff-readability, base64 fallback for binary; multi-exchange URL-keyed).
- [x] 1.3 Define the failure-class taxonomy (A clean-schema / B source-omits-or-JS-or-walled / C schema-lies) as `failure_class` on `case.yaml`; documented in `eval/_capture/README.md`.
- [x] 1.4 Harness homes: replay/assert under `tests/eval_replay/`, capture/refresh + shared format under non-packaged `eval/_capture/`; arch test `tests/architecture/test_eval_not_imported_by_a2web.py` asserts `a2web.*` never imports `eval`.

## 2. Raw-tier replay (MVP)

- [x] 2.1 Implement the centralized `fetch_bytes` replay patch (`harness.patch_fetch_bytes` rebinds every import site; `CassetteMiss` is a loud structured failure with the `make eval-refresh` hint on a miss).
- [x] 2.2 Implement `make eval-capture URL=… Q=… CORPUS=… ID=…` — `eval/_capture/capture.py` runs the real in-process app live, tees every egress into `inputs/`, records answer + contract into `baseline/`, writes `meta.yaml`.
- [x] 2.3 Implement `make eval-replay CORPUS=…` deterministic replay (drives `fetcher.fetch` with cassette resources; `tests/eval_replay/replay.py`).
- [ ] 2.4 Seed the Hepsiburada listing case into a new `regression` corpus via capture; commit the cassette + blessed baseline. **(LIVE — pending a `make eval-capture` run.)**
- [x] 2.5 Deterministic contract test wired into `make check`: `tests/eval_replay/test_selftest_corpus.py` replays the `_selftest` corpus and asserts `contract.json` (proven offline; the `regression` test follows the same shape once 2.4 captures it).

## 3. Browser-tier capture + override

- [x] 3.1 Implement `CassetteBrowserPool` (`harness.py`) serving the frozen `inputs/rendered.html` via `acquire()`; never launches Camoufox. Capture-side `_TeePool` records the rendered DOM.
- [x] 3.2 Implement the eager-capture policy: always freeze raw; eagerly freeze rendered DOM for `commerce`/`js`/`spa`-tagged cases (`capture_case` top-up); on-use otherwise; `--all-tiers` forces eager.
- [x] 3.3 Loud-gap behavior tested: `tests/eval_replay/test_loud_gap.py` — a tier with no frozen entry raises `CassetteMiss` (case id + tier + refresh command), makes no live call.

## 4. LLM-as-egress recording

- [x] 4.1 Implement `CassetteLlm` (`harness.py`) serving a recorded provider response from `inputs/llm/*.json`; capture-side `_TeeExtractor` records it.
- [ ] 4.2 Decide and document the LLM-recording key (prompt-hash vs (url, tier)) so it coexists with the `EXTRACT_*` cache prefix (coordinate with change `multi-source-extraction-input`). **(MVP uses a single recorded response per case; multi-call keying deferred to the first multi-LLM-call case.)**
- [ ] 4.3 Extend the deterministic contract test to assert byte-exact answer + exact token cost under full LLM replay. **(Lands with the first `ask` regression case — needs 2.4's live LLM recording.)**

## 5. Breaking corpus + refresh/bless

- [ ] 5.1 Add `breaking` corpus cases spanning class A, B, and C (each declaring its class); capture cassettes + baselines. **(LIVE — pending `make eval-capture` runs.)**
- [x] 5.2 Implement `make eval-refresh CASE=…` — `eval/_capture/refresh.py` re-captures `inputs/`, re-runs the diff of the fresh answer + contract vs blessed `baseline/`; never overwrites without bless.
- [x] 5.3 Implement the `A2WEB_BLESS_EVAL=1` re-bless path (`tests/eval_replay/bless.py` + `refresh.py`), mirroring the `A2WEB_BLESS_CONTRACTS=1` idiom.

## 6. Bench split + judge pinning

- [ ] 6.1 Split the existing `make bench` (`python -m a2web.llm_eval`) lane so LLM-judged axes (answer quality, clarity, next_links) stay live/informational and do not gate `make check`.
- [ ] 6.2 Pin and record the judge model id in the `make bench` run report.

## 7. Validate the instrument + wrap

- [ ] 7.1 Prove the substrate works end-to-end: replay the Hepsiburada regression case deterministically twice and confirm byte-identical answer/tier/token output.
- [ ] 7.2 Update `docs/architecture/extraction-fidelity-program.md` Status: `eval-substrate` landed; record it as the precondition that unblocks confirming ADR-0004–0007.
- [ ] 7.3 Update `CHANGELOG.md` and the `test-layout` / `output-benchmark` capability docs to reflect the corpus/replay homes and the make-check vs make-bench rule.
- [ ] 7.4 Run `make check` green (lint + ty + test-cov + arch).
