## 1. Lock the bugs in with failing tests first

- [x] 1.1 Add a test calling `Extractor.extract(..., request_routing=True, request_next_links=True)` against a fake provider — the combination `query` uses and that `grep -rn "request_routing=True" tests/` proves has zero coverage. Assert the rendered prompt contains no fence instruction and no `{"anchor": ..., "url": ...}` exemplar. MUST fail before any src change.
- [x] 1.2 Add a test where the fake provider returns prose + a ` ```next_links ` fenced JSON array on the routing path (verbatim from the live bad response in `proposal.md`). Assert `ExtractionResult.answer` has no ` ```next_links ` substring. MUST fail before the fix.
- [x] 1.3 Add a jina test whose stub body exceeds 2048 bytes (pad the markdown region past `_STUB_MAX_BODY`) and assert `verdict=not_found, status_code=404, pre_rendered is None`. MUST fail before the fix — this is the D6 non-vacuity assertion that a reintroduced ceiling cannot pass.
- [x] 1.4 Confirm the existing quoted-stub test (`test_jina_tier.py:101`) still passes, and extend it so the quotation sits after a `Markdown Content:` separator in a body well OVER 2048 bytes — proving the replacement guard closes the false positive without leaning on length.

## 2. Fix the extraction contradiction

- [x] 2.1 In `extractor.py:213`, gate the `_next_links_suffix(...)` append on `not request_routing` so the router path requests exactly one output contract (design D1). Leave both flags independent in the signature.
- [x] 2.2 Restructure the `if request_routing / elif request_next_links` branch (`extractor.py:270-279`) so fence-stripping runs on BOTH paths rather than only the `elif` (design D2). Keep `parsed_next_links = []` on the routing path — `other_pages` owns that data there.
- [x] 2.3 Change `_split_answer_and_routing`'s `except ParseError: return text, None` (`extractor.py:526-529`) to return sanitized text, not the raw model response (design D3).
- [x] 2.4 Emit exactly one `llm_wobble` event with `boundary="routing"` on the parse-failure path, and record the routing-requested-but-lost fact on `ExtractionResult` for downstream envelope use.
- [x] 2.5 Verify tasks 1.1 and 1.2 now pass.

## 3. Fix the jina stub decode

- [x] 3.1 Replace `_STUB_MAX_BODY` and the `len(markdown) < _STUB_MAX_BODY` guard (`jina.py:37`, `:148`) with a header-region scoped search: match the stub only before the `Markdown Content:` separator (design D4). Delete the constant so it cannot be reintroduced by habit.
- [x] 3.2 Implement the no-separator fallback — treat the whole response as header and search it in full.
- [x] 3.3 Update the explanatory comment at `jina.py:29-35` to record WHY length was the wrong measurement, naming a2web's own `X-Return-Format: markdown` header as what disarmed it. Future readers must not re-derive a ceiling.
- [x] 3.4 Verify tasks 1.3 and 1.4 now pass.

## 4. Surface the lost index on the envelope — DEFERRED

Attempted and reverted. `routing_lost` is recorded on `ExtractionResult` and fires
an `llm_wobble` event (task 2.4), but is NOT wire-visible.

- [x] 4.1 Resolved by evidence instead of by default: a dedicated `index_lost` hint at `warning` + a `high`→`medium` confidence cap was implemented, and it fired on EVERY `query` whose model did not return a router envelope — 6 frozen wire goldens changed, including `query_success_minimal`. That is the common case, not the exceptional one, so the hint would have been permanent background noise: trading one wire defect for another. Reverted.
- [~] 4.2 Deferred — the signal exists on `ExtractionResult` for a future, evidence-led decision.
- [~] 4.3 Deferred — needs a discriminator between "model never emits router JSON" (routine, not worth a hint) and "model emitted a malformed envelope" (worth one). That discriminator does not exist yet.
- [~] 4.4 Deferred with 4.2/4.3.

## 5. Close the wire guarantee

- [x] 5.1 Add a `call_text`-channel assertion that `answer` carries no fenced block across the frozen `query` wire cases. Use `call_text`, not `call_wire` — the agent's view is the point, per the two-channel rule in CLAUDE.md.
- [x] 5.2 Wire golden gate run: **ZERO deltas**. The only deltas that appeared came from the group-4 hint, which was reverted — the two actual bugfixes change no frozen surface.
- [x] 5.3 Confirm the accepted-delta table's own guard (`test_every_accepted_delta_is_real`) still passes.

## 6. Never lose a case

- [x] 6.1 Add a corpus entry for the dead-URL case (the live 404 from `proposal.md`), with `criteria` phrased against stable structural facts: a 404 URL must not return `confidence: high` with no `status`. Phrase so it survives the site fixing or removing the page.
- [x] 6.2 Add a corpus entry for the fence case: a `query` answer must never contain a fenced block.

## 7. Verify

- [x] 7.1 `make check` green (lint + ty + test, coverage ≥85%).
- [x] 7.2 `make arch` green — confirm no architecture walk went vacuous.
- [x] 7.3 Run the **targeted bench**, not the full matrix (design D7 — quota-constrained). Capture a before/after pair around the D1 prompt change:

      make bench ARGS="--mode detail --axis next_links \
        --slug hn-front --slug gh-trending \
        --slug hepsiburada-reviews-drilldown-on-page \
        --slug amazon-product-reviews-elsewhere"

      4 cells on one system with one judged axis, versus 29 × 3 systems × 3 axes for the full run. The deterministic token + contract axes still run — they cost nothing — so contract conformance is covered for free. Keep `A2WEB_BENCH_PROVIDER=claude-code` (the Makefile default): subscription, never the metered API (ADR-0016).
- [x] 7.4 Write findings to `eval/findings_<date>.md`, recording that this was a targeted subset and naming the slugs, so a future reader does not mistake it for full-matrix evidence. If `next_links`/`other_pages` quality regressed on the affordance slugs, revisit D1 before landing — that is the specific failure D1 could cause.
- [x] 7.5 Re-run the original live query against the `bhklima.com` URL and confirm it now returns a failure-shaped envelope with a `content_not_found` hint and a fence-free answer.
