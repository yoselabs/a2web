# Tasks

## 1. Prove the failure before fixing it

- [ ] 1.1 Add a failing test in `tests/capabilities/output_benchmark/` that builds a
      real `AskResponse` with a populated `other_pages` set, dumps it through the
      production serializer, and asserts the candidate-block reader finds it. It MUST
      fail on today's code (D5). Record the failure output in the commit message.
- [ ] 1.2 Add the vacuity floor beside it: assert the constructed candidate set is
      non-empty, so the test cannot pass by finding nothing in nothing.
- [ ] 1.3 Add a failing test asserting that an axis requested on ≥1 cell and scored on
      0 is reported as broken. It MUST fail today.

## 2. Typed axis outcome (D1)

- [ ] 2.1 Add the `AxisDisposition` closed enum (`SCORED`/`NOT_APPLICABLE`/`UNSCORED`)
      and the reusable `dataclass(slots=True)` axis-outcome record.
- [ ] 2.2 Replace the flat per-axis sentinel fields on `EvalRow` with the record for
      all four axes plus `next_links`. Delete the old fields — do not shadow them.
- [ ] 2.3 Update `_row_to_json` and `_RESULTS_FIELDS` to flatten at write time, so
      `results.tsv` and `results.json` keep a flat shape without the model carrying one.
- [ ] 2.4 Set the disposition at each of the three silent return sites in
      `_score_next_links`, and at the `JudgeParseError` site in the quality axis.

## 3. Candidate-field resolution (D2)

- [ ] 3.1 Add the literal `_CANDIDATE_FIELD` system→field table with a docstring citing
      ADR-0015 and this failure.
- [ ] 3.2 Make `_next_links_block` resolve through the table instead of assuming
      `next_links`.
- [ ] 3.3 Add a build-time check that every registered eval system appears in the
      table, so a new system cannot join with an unscored axis.
- [ ] 3.4 Confirm 1.1 and 1.3 now pass.

## 4. Denominators and coverage in the report (M4)

- [ ] 4.1 Render coverage for `quality` and `clarity` in `_write_axes`, matching the
      form `contract` and `next_links` already use.
- [ ] 4.2 Split the `—` glyph: an axis with no applicable cells renders differently
      from an axis that was requested and scored nothing.
- [ ] 4.3 Add a coverage section to `findings.md` listing, per axis, cells scored /
      not-applicable / unscored-with-reason.
- [ ] 4.4 Add a test that a mean is never rendered without its coverage.

## 5. Broken-axis reporting (D3)

- [ ] 5.1 After all artifacts are written, detect any axis with ≥1 requested and 0
      scored cells.
- [ ] 5.2 Report it by name in `findings.md`, in the stdout summary, and via a
      non-zero exit. Artifacts MUST already be on disk before the exit path runs.
- [ ] 5.3 Test that a broken axis still leaves a complete artifact directory.

## 6. Cache mode (D4, M7)

- [ ] 6.1 Add the settings flag that makes `LlmExtractorResource` build
      `Extractor(cache=None)` instead of an `LlmCache`.
- [ ] 6.2 Thread a bypass flag through the bench CLI in `llm_eval/__main__.py`.
- [ ] 6.3 Record the cache mode in `manifest.json`.
- [ ] 6.4 Test that the bypass flag yields an extractor with no cache, and that the
      manifest records the mode either way.

## 7. Specs and gate

- [ ] 7.1 `make check` green, coverage ≥85%.
- [ ] 7.2 `uv run tach check` clean; `make arch` green.
- [ ] 7.3 Confirm every new guard has been watched failing (tasks 1.1–1.3) and that
      each carries a non-vacuity assertion.

## 8. Evidence — the re-run

- [ ] 8.1 Full-corpus `make bench` on a subscription provider (ADR-0016;
      `A2WEB_BENCH_PROVIDER=claude-code-sdk`). Confirm `next_links` reports real
      scores on the `next_links_expected` cases rather than `None`.
- [ ] 8.2 Write `eval/findings_<date>.md` comparing the new run against
      `eval/runs/2026-07-22_024912/`, stating which deltas are the revived axis and
      which are product changes since 2026-07-22.
- [ ] 8.3 Record any product defect the revived axis surfaces as a BACKLOG entry or a
      corpus case. Do NOT fix it inside this change.
- [ ] 8.4 Update BACKLOG.md: mark M3, M4, M7 closed; note that M8 and the quality-0
      expected-failure cells remain open and are sequenced behind the corpus change.
