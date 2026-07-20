## ADDED Requirements

### Requirement: Provider failure during extraction surfaces its cause

When `Extractor.extract()` catches an `AnyLLMError` from `provider.complete(...)`, it
SHALL preserve today's empty-Completion degrade seam (it SHALL NOT begin raising an
exception to downstream callers that never previously saw one), but it SHALL NOT
silently discard the failure. Specifically:

1. The catch site SHALL emit an `await a2kit.log.warning(...)` typed event naming the
   failure (model id + the provider error message) so a live extraction outage is
   visible to operators — matching the `ResourceUnavailable` path, which already
   surfaces a cause. Swallowing the error with no trace SHALL NOT occur.
2. `ExtractionResult` SHALL carry the provider error message on a typed field (e.g.
   `provider_error: str | None`, defaulting `None`), populated from the caught
   `AnyLLMError` (the same string captured in `Completion.raw["error"]`). This field
   SHALL be `None` on every successful extraction and on a genuine on-contract empty
   answer. It is the signal the orchestrator consults to distinguish a provider failure
   from a parse/empty failure — no consumer re-derives it from the answer text.

The single flat `AnyLLMError` (anyllm exposes no `retryable`/`status_code` taxonomy)
means this requirement surfaces the *message* only; it SHALL NOT attempt
transient-vs-terminal classification of the error.

#### Scenario: A provider error is logged and carried, not laundered

- **WHEN** `provider.complete(...)` raises `AnyLLMError("401 invalid api key")` during
  `Extractor.extract()`
- **THEN** a `warning`-level typed log event fires naming the model and the message,
  and the returned `ExtractionResult` has `answer == ""` and
  `provider_error == "401 invalid api key"`

#### Scenario: A successful extraction carries no provider error

- **WHEN** `provider.complete(...)` returns a non-empty answer
- **THEN** the returned `ExtractionResult` has `provider_error is None`

#### Scenario: A genuine on-contract empty answer is not a provider error

- **WHEN** `provider.complete(...)` returns successfully with empty text (the model
  produced no answer without erroring)
- **THEN** the returned `ExtractionResult` has `answer == ""` and `provider_error is None`
  (the orchestrator classifies this as `extraction_empty`, not `llm_error`)
