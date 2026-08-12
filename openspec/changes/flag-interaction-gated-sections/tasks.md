# Tasks — flag-interaction-gated-sections

## 1. Tenet and vocabulary

- [ ] 1.1 Add `docs/adr/0020-grounded-absence-never-contradict-the-page.md` (already written) to `docs/adr/INDEX.md`.
- [ ] 1.2 Add the tenet to `AGENTS.md` "Never" as a one-liner citing ADR-0020.
- [ ] 1.3 Add `interaction_required` to `HINT_CODES` and write its factory in `hints.py`, with a docstring stating why it is not `section_unretrieved` (opposite fix) and why it is `warning` not `critical`.
- [ ] 1.4 Confirm `test_every_hint_code_has_a_factory` / `test_hint_codes_are_declared` pass.

## 2. Detection

- [ ] 2.1 Capture a fixture of the motivating page's raw HTML into `tests/fixtures/captured/` (fixtures are CAPTURED, never hand-written).
- [ ] 2.2 Write the DOM predicate over `fc.body` with `selectolax`: `role="tab"` + `aria-controls` → absent/empty panel; `aria-expanded="false"`; `<details>` without `open`. Capture label + adjacent source-stated count.
- [ ] 2.3 Exclude candidates inside `role="nav"` regions (cart/notification badges).
- [ ] 2.4 New phase module in `fetcher/sufficiency/`, mirroring `_phase_listing_completeness`; typed field on `FetchContext`, never `dict[str, Any]`.
- [ ] 2.5 Wire the phase into **both** call sites (`comprehension/extract.py` and `retrieval/escalate/seam.py`) with a symmetric clear.
- [ ] 2.6 Negative fixtures: price, rating, pager, cart badge — assert none is detected as a gate.
- [ ] 2.7 Assert the markdown-only tiers do not manufacture a gate (declared coverage limit).

## 3. Relevance

- [ ] 3.1 Inject detected gates into the extractor input as grounded handles, following the page-link digest mechanism (ADR-0013). Bump the prompt version.
- [ ] 3.2 Add the router-schema field for selecting the blocking gate; the model may only return a detected handle.
- [ ] 3.3 Server-side: reject/ignore any returned handle not in the detected set — a gate label absent from the page must never reach the wire.
- [ ] 3.4 Test the cross-language case explicitly (English question, Turkish label, zero token overlap) — this is the case a deterministic matcher fails.

## 4. Envelope

- [ ] 4.1 Emit the hint and cap `confidence` `high → medium` in `build_ask_response`, alongside `query_title_mismatch`.
- [ ] 4.2 Assert the cap never raises, and never reaches `low`.
- [ ] 4.3 Assert `retrieval_incomplete` stays absent and `status` is unchanged — a gated section must not fail the fetch.
- [ ] 4.4 Assert a non-blocking gate yields an envelope byte-identical to today's.
- [ ] 4.5 Assert `also_here` never lists a gated section.
- [ ] 4.6 Assert no `section_unretrieved` hint is emitted for a gated section.

## 5. Declaration

- [ ] 5.1 Docstring on `Confidence`: retrieval quality, not answer trust.
- [ ] 5.2 One sentence each in the `query` tool description (`routers.py`): what `confidence` grades, and that `operator_hints[].code` is the branching surface.
- [ ] 5.3 Test that both statements are present in the served tool description.

## 6. Verification

- [ ] 6.1 Capability test under `tests/capabilities/`, tagged `@pytest.mark.protects` with an identifier that already exists (`change:flag-interaction-gated-sections`).
- [ ] 6.2 Confirm no CLI-contract delta (`tests/contracts/cli/`) and no wire-golden re-bless is required.
- [ ] 6.3 Add the motivating case to `eval/corpus.yaml`, phrased against stable structural facts — the page states a Q&A count, and the envelope must not assert the source has none.
- [ ] 6.4 `make check` (coverage ≥85%), then `make bench` — this change touches extraction and envelope shape-adjacent behavior, so the benchmark is required, and every new failure is captured in `eval/corpus.yaml` the same session.

## 7. Follow-ups (file as beads, do NOT implement here)

- [ ] 7.1 General `query_unanswered` flag — requires a producer census before `false` is meaningful (ADR-0009 §46).
- [ ] 7.2 ADR-0017 amendment: the severity ladder has no rung for *verified AND must-act*.
- [ ] 7.3 `FetchStatus.partial` is declared on the wire contract and produced nowhere.
- [ ] 7.4 Verify `reddit_forbidden_try_archive` / `reddit_deleted_try_archive` (both `info`, severity dropped from the wire) escalate on the terminal path when the suggested archive fallback also fails.
- [ ] 7.5 `hepsiburada.com` absent from `_JS_HEAVY_HOSTS_SEED` while `trendyol.com` / `aliexpress.com` are present.
