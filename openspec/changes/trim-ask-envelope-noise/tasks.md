# Tasks

Carried from `envelope-wire-hygiene` §4 (its §1/§3 died with a2kit; §2's dispatch-
encoder test is now a2web-owned in `wire.py` and green). Breaking for parsers —
the tier decision is a human call.

## 1. Decide the trim (human-gated)
- [ ] 1.1 Dump the current default-path `query` envelope on a representative set
      (success, listing, failure, empty-unverified) and list every field present.
- [ ] 1.2 Per field, decide: keep on default wire / demote to `debug=True` only /
      drop. Candidates: `confidence`, `tier`, failure-story fields, residual meta.
      Record the rationale per field. `answer` + ADR-0015 index are untouchable.

## 2. Apply
- [ ] 2.1 Implement in `models.py` (`AskResponse` field tiers + `_prune_wire`),
      keeping the wire-only serializer contract (flat attribute access preserved
      for eval harness / `build_ask_response`).
- [ ] 2.2 `make check` green — update the four-axis output-benchmark envelope-shape
      assertions to the new shape.

## 3. Prove
- [ ] 3.1 `make bench` under the ADR-0016 subscription provider (never metered):
      confirm the clarity axis rose or held and answer-quality/contract did not
      regress. Write findings to `eval/findings_<date>.md`.
