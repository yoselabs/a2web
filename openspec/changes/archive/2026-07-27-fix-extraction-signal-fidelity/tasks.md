# Tasks

> Unblocked: `restore-llm-fixture-fidelity` landed and was archived
> (`openspec/changes/archive/2026-07-27-restore-llm-fixture-fidelity/`), so the
> replay harness now exercises the recovered branch and goldens can be trusted.

## 1. Shelf — `llm-wobble` EVOLVE: the `OPTIONAL` tolerance

- [x] 1.1 Resolved the shelf loop, worktree `../shelf-a2web`, classified EVOLVE (additive, resolution 0007 monotonic — exposes more, removes nothing).
- [x] 1.2 Added `WobbleTolerance.OPTIONAL`: substitutes `policy.default`, emits NO `llm_wobble`, and is NOT listed in `recovered_fields` (nothing was repaired).
- [x] 1.3 `DEFAULT` unchanged. The load-bearing test drives both tolerances against the SAME absent field and asserts they agree on the value and differ ONLY on the event, so they cannot silently converge.
- [x] 1.4 Shelf gate green (465 passed); tagged `llm-wobble-v0.3.0`, pushed, ledger row `0067` (delivery), `make catalog`. Also corrected the catalog `release` field, stale at v0.1.0 since the v0.2.0 delivery.
- [x] 1.5 Repointed a2web's pin; `uv lock` + `uv sync`.

## 2. Triage the policy table

- [x] 2.1 Reclassified the five contract-optional router fields as `OPTIONAL`, each carrying the prompt clause that justifies it.
- [x] 2.2 Audited every remaining `DEFAULT`. Calls recorded in-file:
  - `structural_form` / `shape` → stay `DEFAULT`. The prompt says `(required)`; dropping them IS the wobble, and it is the `unclassified` arm.
  - `reasoning` (judge, bench clarity, bench next_links) → stay `DEFAULT`. Decorative is not optional: all three prompts request it unconditionally.
  - Nothing else was optional. Triage was against the prompt text, not against observed frequency.
- [x] 2.3 Regression test: the healthy envelope emits ZERO `llm_wobble` events (was five). Paired with a test that a dropped `structural_form` still reports, so silence cannot be achieved by disconnecting the boundary.

## 3. `RoutingOutcome`

- [x] 3.1 Added the StrEnum + `routing_outcome` on `ExtractionResult`.
- [x] 3.2 Classified at the split site. `provider_error` is checked FIRST: a dead provider returned no text, so its unparsable-looking result is not an LLM formatting fact.
- [x] 3.3 DELETED `routing_lost` and every reference. It was written by the extractor and read by NOTHING — a field with no consumer, which is part of why its conflation went unnoticed.
- [x] 3.4 Six per-arm tests in `tests/packages/llm_extract/test_routing_outcome.py`, each driven by a double that declares its `DOUBLES_ARM` and is verified by the fidelity check to actually produce it.

## 4. Decouple the index from the classification

- [x] 4.1 Reordered `_build_router_payload`: the index is parsed unconditionally, before the classification is judged. `RouterPayload.structural_form` / `.shape` became `str | None` (and the pydantic mirror likewise) — the payload survives the label.
- [x] 4.2 Options-shelf strictness unchanged: `is_listing` is `routing.structural_form == "listing"`, which a `None` classification fails exactly as `product` does. The footer-megamenu regression suite passes untouched.
- [x] 4.3 Test: 3 `also_here` + 2 `other_pages` with no `structural_form` retains all 5 and reports `unclassified`.

## 5. The index-loss hint

- [x] 5.1 One `warning` `OperatorHint(code="index_lost")` gated on the DELIVERED index being empty across all three sources — NOT on routing loss (design D4).
- [x] 5.2 The fix names the same-URL `fetch_raw` recovery AND that it is cache-served, so the hint does not read as "pay for another fetch".
- [x] 5.3 Suppressed on `provider_error` (already reported) and on `None` (routing never requested).
- [x] 5.4 Test: lost routing WITH mined `next_links` emits NO hint — the measured HN false positive, pinned.
- [x] 5.5 Test: severity is `warning`; no `try_user_browser` from this condition.
- [x] 5.6 Test: `status`, `retrieval_incomplete`, and `answer` are untouched.

## 6. Wire + gate

- [x] 6.1 `make check` green — 1206 passed, 2 deselected.
- [x] 6.2 `make arch` green — 47 passed.
- [x] 6.3 **No goldens moved, and `make bless-wire` was NOT run — there was nothing to bless.** This is the result, not a shortcut: the hint fires only on degraded arms, and every golden now runs the healthy arm because `_StubProvider` was made contract-faithful by the preceding change. The previous attempt at this signal changed SIX goldens including `query_success_minimal` and was abandoned as "permanent noise"; the entire difference is the fixture, not the design. Verified by `git status` / `git diff --stat` over the contract + golden paths returning empty.
- [ ] 6.4 DEFERRED — re-run the live spikes to confirm the arm distribution and the hint's near-zero fire rate. Live-network + LLM quota, so it is not part of `make check`; the offline per-arm tests cover the classification itself. Tracked in BACKLOG.

## 7. UNPLANNED — the funnel never saw malformed PRESENCE (found during 2.1)

The tolerance policies resolve ABSENCE only: `_apply_field` returns early when
the field is present, so a field present with the WRONG TYPE never reaches a
policy and is silently coerced by the boundary builder (an `also_here` that is a
string became `()`, dropping real content with no record anywhere).

This was survivable only while every absence was also being reported. The moment
the five optional fields became `OPTIONAL`, it would have been the LAST remaining
way for a supplied index to vanish silently — trading one blind signal for
another, inside the change whose entire purpose is removing blind signals.

- [x] 7.1 `_note_malformed` reports present-but-corrupt `also_here` / `other_pages` / `refinement_axes` at the builder.
- [x] 7.2 Test: a malformed `also_here` emits exactly one `llm_wobble`; the healthy envelope still emits zero.
- [x] 7.3 Both delta specs amended to state the split as implemented, rather than asserting funnel behaviour that does not exist.

## 8. Record what was NOT built

- [x] 8.1 `BACKLOG.md`: constrained decoding — blocked on `anyllm` exposing `response_format`/`tool_choice`, and it cannot cover the `claude-code` adapters ADR-0016 makes the default.
- [x] 8.2 `BACKLOG.md`: the `arxiv` no-index-from-any-source finding; cross-references corpus case `listing-answer-always-leaves-an-index`.
- [x] 8.3 Retire the now-wrong BACKLOG entry "Wire-visible signal for a lost router payload" — superseded here.
- [x] 8.4 `BACKLOG.md`: the `llm_wobble` logger-binding EVOLVE (`llm_wobble.bind(logger=...)`) — a2web's 3 wrapper functions duplicate the shelf signature and will drift.
