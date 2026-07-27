# Tasks

## 1. Prove the failure before fixing it

- [x] 1.1 Add a failing test in `tests/capabilities/output_benchmark/` that builds a
      real `AskResponse` with a populated `other_pages` set, dumps it through the
      production serializer, and asserts the candidate-block reader finds it. It MUST
      fail on today's code (D5). Record the failure output in the commit message.
- [x] 1.2 Add the vacuity floor beside it: assert the constructed candidate set is
      non-empty, so the test cannot pass by finding nothing in nothing.
- [x] 1.3 Add a failing test asserting that an axis requested on ≥1 cell and scored on
      0 is reported as broken. It MUST fail today.

## 2. Typed axis outcome (D1)

- [x] 2.1 Add the `AxisDisposition` closed enum (`SCORED`/`NOT_APPLICABLE`/`UNSCORED`)
      and the reusable `dataclass(slots=True)` axis-outcome record.
- [x] 2.2 Replace the flat per-axis sentinel fields on `EvalRow` with the record for
      all four axes plus `next_links`. Delete the old fields — do not shadow them.
- [x] 2.3 Update `_row_to_json` and `_RESULTS_FIELDS` to flatten at write time, so
      `results.tsv` and `results.json` keep a flat shape without the model carrying one.
- [x] 2.4 Set the disposition at each of the three silent return sites in
      `_score_next_links`, and at the `JudgeParseError` site in the quality axis.

## 3. Candidate-field resolution (D2)

- [x] 3.1 Add the literal `_CANDIDATE_FIELD` system→field table with a docstring citing
      ADR-0015 and this failure.
- [x] 3.2 Make `_next_links_block` resolve through the table instead of assuming
      `next_links`.
- [x] 3.3 Add a build-time check that every registered eval system appears in the
      table, so a new system cannot join with an unscored axis.
- [x] 3.4 Confirm 1.1 and 1.3 now pass.

## 4. Denominators and coverage in the report (M4)

- [x] 4.1 Render coverage for `quality` and `clarity` in `_write_axes`, matching the
      form `contract` and `next_links` already use.
- [x] 4.2 Split the `—` glyph: an axis with no applicable cells renders differently
      from an axis that was requested and scored nothing.
- [x] 4.3 Add a coverage section to `findings.md` listing, per axis, cells scored /
      not-applicable / unscored-with-reason.
- [x] 4.4 Add a test that a mean is never rendered without its coverage.

## 5. Broken-axis reporting (D3)

- [x] 5.1 After all artifacts are written, detect any axis with ≥1 requested and 0
      scored cells.
- [x] 5.2 Report it by name in `findings.md`, in the stdout summary, and via a
      non-zero exit. Artifacts MUST already be on disk before the exit path runs.
- [x] 5.3 Test that a broken axis still leaves a complete artifact directory.

## 6. Cache mode (D4, M7)

- [x] 6.1 Add the settings flag that makes `LlmExtractorResource` build
      `Extractor(cache=None)` instead of an `LlmCache`.
- [x] 6.2 Thread a bypass flag through the bench CLI in `llm_eval/__main__.py`.
- [x] 6.3 Record the cache mode in `manifest.json`.
- [x] 6.4 Test that the bypass flag yields an extractor with no cache, and that the
      manifest records the mode either way.

## 7. Specs and gate

- [x] 7.1 `make check` green, coverage ≥85%.
- [x] 7.2 `uv run tach check` clean; `make arch` green.
- [x] 7.3 Confirm every new guard has been watched failing (tasks 1.1–1.3) and that
      each carries a non-vacuity assertion.

## 8. Evidence — the re-run

- [x] 8.1 SUBSET run on a subscription provider (ADR-0016) confirming the axis
      reports: `--only listing --axis next_links --mode detail` on `claude-code-sdk`,
      16 cells, 139 s, $0.66 → `eval/runs/axis-revival-probe`. `next_links` scored
      12 of 16 cells (was 0 of 29). Deliberately scoped to "does the axis report",
      not "how good is a2web".
- [ ] 8.1b Full-corpus run for the actual comparison against
      `eval/runs/2026-07-22_024912/`. ~8 min, all 33 cases x 3 systems, all axes.
      Open — needs a spend decision, and is the only way to read quality/clarity
      deltas or to re-check the four cases that never ran on 2026-07-22.
- [x] 8.2 `eval/findings_2026-07-28.md` written, stating explicitly what the subset
      run does NOT establish (quality, clarity, the M8 quality-0 cells, non-listing
      classes, and independence — cache mode was ON).
- [x] 8.3 Recorded in BACKLOG, not fixed: `listing-answer-always-leaves-an-index`
      emits no index on either system (ADR-0015, corroborates the 2026-07-27
      `wikipedia-narrow-ask-indexes` finding by an independent route); `reddit-listing`
      likewise; and the axis's first-ever quality baseline (mean 3.17).
- [x] 8.4 BACKLOG.md updated: M3, M4, M7 closed; M1, M2, M5, M6, M8 and H1/H3/H4/H5
      explicitly still open.
