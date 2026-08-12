# Tasks — flag-interaction-gated-sections

## 1. Tenet and vocabulary

- [x] 1.1 Add `docs/adr/0020-grounded-absence-never-contradict-the-page.md` (already written) to `docs/adr/INDEX.md`.
- [x] 1.2 Add the tenet to `AGENTS.md` "Never" as a one-liner citing ADR-0020.
- [x] 1.3 Add `interaction_required` to `HINT_CODES` and write its factory in `hints.py`, with a docstring stating why it is not `section_unretrieved` (opposite fix) and why it is `warning` not `critical`.
- [x] 1.4 Confirm `test_every_hint_code_has_a_factory` / `test_hint_codes_are_declared` pass.

## 2. Detection

- [x] 2.1 Capture a fixture of the motivating page's raw HTML into `tests/fixtures/captured/` (fixtures are CAPTURED, never hand-written). `hepsiburada_carraro_gravel_g2_tabs.html` — captured live via a real browser's hydrated DOM, ground-truth verified for both the gated Q&A panel (empty) and the Reviews panel (populated, the negative control).
- [x] 2.2 Write the DOM predicate over raw HTML with `selectolax`: `role="tab"` + `aria-controls` → absent/empty panel; `<details>` without `open`. Capture label + adjacent source-stated count (`src/a2web/gated_sections.py`). Real captured markup uses `aria-selected` not `aria-expanded`; the predicate follows the verified shape, not the originally assumed one.
- [x] 2.3 Exclude candidates inside `role="nav"` regions (cart/notification badges).
- [x] 2.4 New phase module in `fetcher/sufficiency/gated_sections.py`, mirroring `_phase_listing_completeness`; typed field (`gated_sections: tuple[GatedSection, ...]`) on `FetchContext`, never `dict[str, Any]`.
- [x] 2.5 Wire the phase into the same three call sites `_phase_listing_completeness` uses (`comprehension/extract.py` ×2, `retrieval/escalate/seam.py` ×1). Symmetric clear is implicit: the phase recomputes from scratch on every call rather than accumulating.
- [x] 2.6 Negative fixtures: price, rating, pager, cart/notification badge — assert none is detected as a gate (`test_gated_sections_detector.py`).
- [x] 2.7 Assert markdown-only bodies do not manufacture a gate (declared coverage limit) — same file.

## 3. Relevance

- [x] 3.1 Inject detected gates into the extractor input as grounded handles (`## gated sections` digest, `fetcher/answer/digest.py::_build_gate_digest`), mirroring the page-link digest mechanism (ADR-0013). Prompt version bumped 7 → 8 (`prompts.py`); `Extractor.extract()` and `LlmExtractorResource.extract()` both gained a `gate_digest` parameter.
- [x] 3.2 Router-schema field `blocked_gate: int | None` added to the boundary `RouterPayload` (`router_payload.py`) and parsed in `extractor.py::_build_router_payload`; wobble policy added (`wobble/_policies.py`, `OPTIONAL`).
- [x] 3.3 Server-side closed-set resolution in `fetcher/answer/digest.py::_resolve_blocked_gate` — an unknown handle logs `llm_wobble` and resolves to `None`, never a fabricated section. Covered by `test_an_unknown_handle_is_dropped_not_fabricated`.
- [x] 3.4 Cross-language mechanism proven end-to-end (`test_gated_section_end_to_end.py`, English query + Turkish `Soru Cevap` label, zero token overlap by construction) — the MECHANISM (handle-based selection, not term-matching) is proven; a real model's cross-language JUDGMENT quality is an `eval/corpus.yaml` question (§6.3), not a unit-test one, and is explicitly out of scope for a unit test per the design notes.

## 4. Envelope

- [x] 4.1 Emit the hint and cap `confidence` `high → medium` in `build_response` (not `build_ask_response` — the caps this mirrors, `served_url_differs`/`query_title_mismatch`/failed-browser-rung, all live there, shared by `fetch_raw` and `ask`; `fetch_raw` never populates `blocked_gated_section` since it never runs the extractor, so the cap is naturally a no-op there).
- [x] 4.2 Asserted the cap never raises, and never reaches `low` (`test_gated_section_caps_confidence.py`).
- [x] 4.3 Asserted `retrieval_incomplete` stays `False` and `status` is unchanged.
- [x] 4.4 Asserted a non-blocking gate (`blocked_gated_section=None`) yields an untouched envelope.
- [x] 4.5 `also_here` never lists a gated section — true by construction (the gate resolution never writes to `also_here`); not separately unit-tested since there is no code path that could make it true.
- [x] 4.6 Asserted no `section_unretrieved` hint accompanies `interaction_required` — true by construction (different producers; `section_unretrieved` has exactly one caller, the GitHub handler); covered implicitly by every envelope assertion in the new tests never showing both codes.

## 5. Declaration

- [x] 5.1 `Confidence` docstring: retrieval quality, not answer trust (`models.py`).
- [x] 5.2 `query` tool description (`routers.py`) states what `confidence` grades and that `operator_hints[].code` is the branching surface.
- [x] 5.3 `test_confidence_declared_in_tool_description.py` asserts both statements are present in the served description.

## 6. Verification

- [x] 6.1 Capability tests under `tests/capabilities/interaction_gated_sections/`, tagged `@pytest.mark.protects("change:flag-interaction-gated-sections")` (the delta specs are not yet synced into `openspec/specs/`, so a `spec:fetch-response` citation would not resolve — `change:` is correct until `opsx:sync`/archive).
- [x] 6.2 No CLI-contract delta. **One wire-golden delta WAS required** (the original task assumption was wrong): the `query` tool description text changed (§5.2), which is part of `list_tools`'s frozen wire golden. Re-blessed with `A2WEB_ACCEPT_WIRE_DELTA=flag-interaction-gated-sections-tool-description`, recorded in `tests/contracts/DELTAS.md`.
- [x] 6.3 Added `hepsiburada-carraro-gravel-g2-qa-tab-gated` to `eval/corpus.yaml` (new `section-gated` class, distinguished from the existing whole-page-wall `gated` class), phrased against the stable structural fact (the page's own tab strip states a count).
- [x] `make check` (lint + ty + test-cov + arch) — **passing**: 1853 tests, 92.12% coverage, tach clean.
- [ ] `make bench` — **NOT run.** It is live-network and spends real LLM quota/time; per session convention this needs an explicit go-ahead rather than running unprompted. Run it deliberately after this change lands, and capture any new failure in `eval/corpus.yaml` the same session per the standing rule.

## 7. Follow-ups (filed as beads, NOT implemented here)

- [ ] 7.1 General `query_unanswered` flag — requires a producer census before `false` is meaningful (ADR-0009 §46). `a2web-552`.
- [ ] 7.2 ADR-0017 amendment: the severity ladder has no rung for *verified AND must-act*. `a2web-iqr`.
- [ ] 7.3 `FetchStatus.partial` is declared on the wire contract and produced nowhere. `a2web-0br`.
- [ ] 7.4 Verify `reddit_forbidden_try_archive` / `reddit_deleted_try_archive` (both `info`, severity dropped from the wire) escalate on the terminal path when the suggested archive fallback also fails. `a2web-luh`.
- [ ] 7.5 `hepsiburada.com` absent from `_JS_HEAVY_HOSTS_SEED` while `trendyol.com` / `aliexpress.com` are present. `a2web-cid`.
