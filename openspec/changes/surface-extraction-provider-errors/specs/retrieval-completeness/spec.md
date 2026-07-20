## ADDED Requirements

### Requirement: A provider-failure extraction miss carries a distinct llm_error hint

An `ask`/`query` fetch whose verdict is `ok` (real content retrieved) but whose
extraction produced no answer BECAUSE the extraction provider failed
(`ExtractionResult.provider_error` is non-`None`) SHALL be reported with a distinct
`llm_error` operator hint rather than the parse-failure `extraction_empty` hint. The
`llm_error` hint SHALL:

- be `severity: critical` and set `status: failed` + `retrieval_incomplete: true` (the
  ADR-0009 never-silently-miss floor is unchanged — only the stated cause and fix change);
- carry the provider error message (`provider_error`) so the caller sees the real cause,
  not "parse failure";
- name a truthful fix that does NOT falsely promise "rephrase the question" will help:
  the extraction provider errored — check the LLM backend (key / SDK / provider status);
  retrying may help only if the error is transient (e.g. a 5xx overload).

The existing `extraction_empty` hint (retry / `fetch_raw` / rephrase advice) SHALL remain
for the genuine parse/empty case — extraction ran and completed but the answer is empty
with no provider error (`provider_error is None`). Exactly one of the two hints SHALL be
emitted for an unanswered `ask` on retrieved content; they SHALL NOT both fire.

Both hints keep `retrieval_incomplete: true` and `status: failed`; the distinction is
purely which cause+fix story the caller is told.

#### Scenario: A provider failure surfaces llm_error, not extraction_empty

- **WHEN** an `ask` fetch retrieves real content (verdict `ok`) but extraction returned an
  empty answer with `ExtractionResult.provider_error == "529 overloaded"`
- **THEN** the response carries a `critical` `llm_error` hint quoting `529 overloaded`, is
  `status: failed` + `retrieval_incomplete: true`, and does NOT carry `extraction_empty`

#### Scenario: A genuine parse/empty failure keeps extraction_empty

- **WHEN** an `ask` fetch retrieves >500 chars (verdict `ok`) but extraction returned an
  empty answer with `provider_error is None`
- **THEN** the response carries the `extraction_empty` hint (retry / `fetch_raw` / rephrase),
  is `status: failed` + `retrieval_incomplete: true`, and does NOT carry `llm_error`

#### Scenario: Exactly one unanswered-ask hint fires

- **WHEN** an `ask` on retrieved content produces no answer for any reason
- **THEN** the response carries exactly one of `{extraction_empty, llm_error, llm_unavailable}`,
  never two of them for the same miss
