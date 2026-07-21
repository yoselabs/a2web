# Tasks

## 1. Surface the provider error out of the extractor

- [x] 1.1 Add a typed `provider_error: str | None = None` field to `ExtractionResult` in `src/a2web/packages/llm_extract/extractor.py`.
- [x] 1.2 In the `except AnyLLMError as exc` block (extractor.py ~L230), emit `await a2kit.log.warning(...)` naming the model id + `str(exc)`. Keep the empty-Completion degrade (no new raise downstream). Verify no `packages/` → `a2web.<domain>` import is introduced (use the package-side log helper / stdlib logging, not a domain import).
- [x] 1.3 Populate `ExtractionResult.provider_error` from the caught error (the string already in `Completion.raw["error"]`) on the empty-Completion path; leave it `None` on every success and on a genuine on-contract empty answer.

## 2. Split the diagnostic in the orchestrator

- [x] 2.1 Add `llm_error_hint(*, message: str) -> OperatorHint` in `src/a2web/models.py` — `code="llm_error"`, `severity="critical"`, message quoting `provider_error`, `fix` naming the LLM-backend check and "retry only if transient". Model is at module scope (arch invariant).
- [x] 2.2 Thread the provider error to the response builder: carry `result.provider_error` onto `FetchContext` in `fetcher.py::_extract_answer` (a typed field, e.g. `fc.extraction_provider_error: str | None`).
- [x] 2.3 In `fetcher_response.py`, branch the existing `extraction_empty` path: when `fc.extraction_provider_error` is set, append `llm_error_hint(...)` instead of `extraction_empty_hint(...)`; keep `status=failed` + `retrieval_incomplete=True` for both. Ensure exactly one of `{extraction_empty, llm_error, llm_unavailable}` fires per unanswered ask.
- [x] 2.4 Update the `ask_unanswered` narrative/diagnostics_summary reason string to reflect the provider-error case ("extraction provider errored: <msg>") vs the parse-empty case.

## 3. Tests

- [x] 3.1 Unit test (extractor): inject a provider that raises `AnyLLMError`; assert the returned `ExtractionResult` has `answer == ""` and `provider_error == <message>`, and that a `warning` log event fired. Assert a successful call leaves `provider_error is None`.
- [x] 3.2 Response-level test: drive `fetcher.fetch(...)` (or the response builder) with a provider-error extraction and assert the response carries the `llm_error` critical hint (quoting the message), NOT `extraction_empty`, with `status: failed` + `retrieval_incomplete: true`. Add the mirror test asserting a `provider_error is None` empty answer still yields `extraction_empty`.
- [x] 3.3 Assert exactly one unanswered-ask hint fires (never `extraction_empty` AND `llm_error` together).

## 4. Corpus + gate

- [ ] 4.1 Confirm the `reddit-iem-compare` corpus entry (already added to `eval/corpus.yaml` this session) validates against the harness schema; adjust `needs`/`criteria` if the four-axis loader rejects it.
- [x] 4.2 Run `make check` (lint + ty + test, coverage ≥85%). The bench (`make bench`) is live-network — run only if output quality could have moved; this change is diagnostic-only, so bench is optional.
