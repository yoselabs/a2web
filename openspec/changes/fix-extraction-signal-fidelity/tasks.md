# Tasks

> **Blocked on `restore-llm-fixture-fidelity` landing first** (design D6). The
> replay harness currently runs all 16 cases through the degraded branch;
> blessing goldens before that is fixed freezes the lie a second time.

## 1. Shelf — `llm-wobble` EVOLVE: the `OPTIONAL` tolerance

- [ ] 1.1 Resolve the shelf loop (`docs/agent-loop.md`), worktree, classify (expect EVOLVE — additive, resolution 0007 monotonic).
- [ ] 1.2 Add `WobbleTolerance.OPTIONAL`: substitutes the documented empty value and emits NO `llm_wobble` event.
- [ ] 1.3 Keep `DEFAULT` firing for present-but-malformed. Add a test proving the two differ on the same field.
- [ ] 1.4 Shelf gate green; tag, push, merge, ledger rows (delivery + verdict), `make catalog`.
- [ ] 1.5 Repoint a2web's pin; `uv lock`.

## 2. Triage the policy table

- [ ] 2.1 In `_policies.py`, reclassify the genuinely-optional router fields — `obstacle`, `also_here`, `other_pages`, `refinement_axes`, `item_total_seen` — as `OPTIONAL`, each with its reason.
- [ ] 2.2 Audit every remaining `DEFAULT` across all policy tables: genuinely optional, or present-but-malformed? Record the call per field.
- [ ] 2.3 Add the regression test: a healthy envelope carrying only `answer`/`structural_form`/`shape` emits ZERO `llm_wobble` events (currently 5).

## 3. `RoutingOutcome`

- [ ] 3.1 Add the `RoutingOutcome` StrEnum; add `routing_outcome` to `ExtractionResult`.
- [ ] 3.2 Classify at the split site: `recovered` / `unparsable` / `unclassified` / `provider_error`.
- [ ] 3.3 DELETE `routing_lost` and every reference. No shim, no deprecation window.
- [ ] 3.4 Per-arm tests, one each, using doubles that declare `DOUBLES_ARM` (dependency on the fixture change).

## 4. Decouple the index from the classification

- [ ] 4.1 Reorder `_build_router_payload`: parse `also_here` / `other_pages` BEFORE returning on a missing `structural_form` / `shape`.
- [ ] 4.2 Verify the options-shelf gate is unchanged in strictness — a `None` classification suppresses the shelf exactly as `product` does. Re-run the footer-megamenu regression.
- [ ] 4.3 Test: envelope with 3 `also_here` + 2 `other_pages` but no `structural_form` retains all 5 entries and reports `unclassified`.

## 5. The index-loss hint

- [ ] 5.1 Emit one `warning` `OperatorHint` gated on the DELIVERED index being empty (all three sources: routing, mined `next_links`, mined `options`) — NOT on routing loss alone (design D4).
- [ ] 5.2 Message names the same-URL `fetch_raw` recovery and that it is cache-served.
- [ ] 5.3 Suppress on the `provider_error` arm (no double-reporting).
- [ ] 5.4 Test: lost routing WITH mined `next_links` emits NO hint.
- [ ] 5.5 Test: severity is `warning`; no `try_user_browser` from this condition.
- [ ] 5.6 Test: `status` and `retrieval_incomplete` are untouched.

## 6. Wire + gate

- [ ] 6.1 `make check` green.
- [ ] 6.2 `make arch` green.
- [ ] 6.3 Review every golden delta individually; confirm each is the decoupling or the hint and nothing else. Then `make bless-wire SLUG=extraction-signal-fidelity`.
- [ ] 6.4 Re-run the live spikes; confirm the arm distribution and that the hint fires at the expected (near-zero) rate.

## 7. Record what was NOT built

- [ ] 7.1 `BACKLOG.md`: constrained decoding — blocked on `anyllm` exposing `response_format`/`tool_choice`, and note it cannot cover the `claude-code` adapters that ADR-0016 makes the default.
- [ ] 7.2 `BACKLOG.md`: the `arxiv` no-index-from-any-source finding; cross-reference corpus case `listing-answer-always-leaves-an-index`.
- [ ] 7.3 Retire the now-wrong BACKLOG entry "Wire-visible signal for a lost router payload" — superseded by this change.
