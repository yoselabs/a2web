## Why

When the extraction LLM call fails mid-flight (`AnyLLMError` — auth, rate-limit,
provider overload, or a transient claude-code SDK error), the extractor swallows
the exception, converts it to `Completion(text="", raw={"error": str(exc)})`, and
returns a *successful-looking* `ExtractionResult(answer="")`. No log event fires,
and the error string is discarded one function later (`ExtractionResult.raw`
carries only the truncation flag). The orchestrator then sees an empty answer over
real content and emits the generic `extraction_empty` critical hint — "extraction/parse
failure … Retry, use `fetch_raw`, or rephrase the question."

That advice is actively wrong for the provider-failure case: retrying the same broken
provider or rephrasing the question cannot fix a bad key or a dead SDK session, and
the one piece of evidence that would explain the miss (`str(exc)`) has been thrown
away — not even logged. A live extraction outage currently leaves **zero trace**.

Observed in the field: a Reddit comparison thread (Aria 2 vs Starfield 2) fetched
cleanly — both comments present, question trivially answerable — yet returned
`answer: ""` with the misleading `extraction_empty` hint. The content proves the LLM
did not legitimately return empty; a provider error was laundered into a parse-failure
story. This is an ADR-0009 honesty violation at the diagnostic layer: the incompleteness
is real, but its stated cause and fix are false.

## What Changes

- **Carry the provider error out of the extractor.** `Extractor.extract()` propagates
  the `AnyLLMError` message (already captured in `Completion.raw["error"]`) onto
  `ExtractionResult` instead of dropping it. The empty-Completion degrade seam is kept —
  we do not start raising a new exception downstream — but the cause survives.
- **Log the swallowed error.** The `except AnyLLMError` catch emits an
  `await a2kit.log.warning(...)` (a typed event) so a live extraction outage is visible
  to operators, matching the `ResourceUnavailable` path which already attaches a
  cause-naming hint.
- **Split the diagnostic.** `fetcher_response` distinguishes a genuine empty/parse
  failure (`extraction_empty`, retry/rephrase advice fair) from a provider failure
  (new `llm_error` hint code carrying `str(exc)` and advice that names the real fix —
  check the LLM backend; retry only helps if the error is transient like a 529 overload).
  Both remain `critical` + `retrieval_incomplete: true` (the ADR-0009 floor is unchanged);
  only the *story* the caller is told becomes truthful.
- **Corpus + regression capture.** Add the Reddit comparison-thread case to
  `eval/corpus.yaml` (guards genuine extraction emptiness on the happy path) and a unit
  test asserting an injected `AnyLLMError` surfaces as `llm_error` with the message, never
  laundered into `extraction_empty`.

Note: anyllm exposes a single flat `AnyLLMError` (no `retryable`/`status_code`), so this
change does NOT attempt transient-vs-terminal classification — it surfaces the message and
softens the "retry" advice to "retry only if transient." Reliable retry-routing is out of
scope and noted as a follow-up should anyllm grow an error taxonomy.

## Capabilities

### New Capabilities
_(none — this extends existing behavior)_

### Modified Capabilities
- `extraction`: the extractor MUST surface a provider-failure cause rather than
  silently returning an empty answer with the error discarded; the swallowed
  `AnyLLMError` MUST be logged.
- `retrieval-completeness`: an extraction miss caused by a provider failure MUST carry
  a distinct `llm_error` operator hint (with the provider message and a truthful fix),
  separate from the parse-failure `extraction_empty` hint. Both stay critical +
  `retrieval_incomplete`.

## Impact

- Code: `src/a2web/packages/llm_extract/extractor.py` (propagate + log the error),
  `src/a2web/fetcher.py` (`_extract_answer` phase reads the new cause),
  `src/a2web/fetcher_response.py` (split the hint), `src/a2web/models.py` (new
  `llm_error_hint`).
- Tests: `eval/corpus.yaml` (new case), a unit test under `tests/` for the laundering guard.
- No dependency changes. No tool-signature or response-envelope shape change — a new
  operator-hint *code* is additive within the existing `operator_hints` array.
