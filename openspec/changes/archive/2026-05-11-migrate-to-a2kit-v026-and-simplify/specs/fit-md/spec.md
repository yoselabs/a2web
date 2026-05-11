## REMOVED Requirements

### Requirement: Pruning filter produces fit_md

**Reason:** Research confirmed that trafilatura's native extraction pipeline already performs DOM-based boilerplate stripping (headers, footers, ads, blogrolls, recurring elements) before emitting markdown — producing output documented as ~67% smaller than raw HTML. Our `fit-md` runs a second-pass density filter on already-cleaned text; the marginal value is small, and the algorithm was originally crawl4ai's `PruningContentFilter` (the dep we explicitly dropped for weight).

**Migration:** Delete `src/a2web/extract/pruning_filter.py` and the `_phase_fit` phase from the orchestrator. Use trafilatura options at the extraction call site:

```python
extract_markdown(
    html,
    url,
    options=ExtractOptions(
        include_comments=False,
        include_tables=False,
        prune_xpath=[...site-specific selectors if needed...],
    ),
)
```

`FetchResponse.fit_md` field is preserved for backward compatibility (set equal to `content_md`); after one minor version it MAY be removed.

**Validation gate:** Before deletion, all v0.1.0 fit-md fixtures SHALL be re-run through plain trafilatura with the new options. If >5% of fixtures regress on token count by >20%, the deletion is demoted to "keep a thin ~30 LOC post-filter" instead of full removal. If validation passes, full delete.

## ADDED Requirements

### Requirement: fit_md field preserved for backward compat

`FetchResponse.fit_md: str | None` SHALL remain on the response model. When extraction succeeds, `fit_md` SHALL equal `content_md` (no separate pruning pass). When extraction fails or content_md is empty, `fit_md` SHALL be `None`.

This requirement exists ONLY to avoid a wire-shape change for downstream consumers. It MAY be removed in a follow-up change that updates the response shape major-version.

#### Scenario: fit_md equals content_md on success

- **WHEN** extraction succeeds on a typical article fixture
- **THEN** `response.fit_md == response.content_md`

#### Scenario: fit_md is None on extraction failure

- **WHEN** extraction returns empty `content_md` (e.g., gate verdict ≠ ok)
- **THEN** `response.fit_md is None`

### Requirement: Validation regression test

The change SHALL include a regression test that loads every fixture file under `tests/fixtures/fit_md/` (or wherever the v0.1.0 fit-md fixtures live), runs both the v0.1.0 fit-md pipeline and the new trafilatura-options-only pipeline, and asserts: per-fixture token-count regression is ≤ 20%, AND the count of fixtures with any regression is ≤ 5% of the total.

If this regression test fails when the change lands, the migration SHALL revert to keeping a thin ~30 LOC post-filter (the trimmed fit-md) rather than full removal.

#### Scenario: Validation passes → full delete

- **WHEN** the regression test runs against every v0.1.0 fit-md fixture
- **THEN** the assertion holds (≤ 5% of fixtures regress, regression amount ≤ 20%) AND `src/a2web/extract/pruning_filter.py` does not exist after the change

#### Scenario: Validation fails → demoted partial-drop

- **WHEN** the regression test would fail against the new trafilatura-only pipeline
- **THEN** the migration is demoted: `src/a2web/extract/pruning_filter.py` shrinks to ≤ 40 LOC implementing a minimal post-filter, the orchestrator's `_phase_fit` is preserved, AND a deferred backlog item is added to revisit
