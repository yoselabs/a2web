## 1. Resolve open design questions

- [x] 1.1 Confirm `StopLiveTiers` semantics (stops further live `TIER_ORDER` tiers; `RetryViaArchive` still permitted) and finalize the `Action` vocabulary names. — Confirmed: `StopLiveTiers` halts further `TIER_ORDER` dispatch, archive still allowed.
- [x] 1.2 Get sign-off on adding Hypothesis as a dev-only dependency for the projection property tests. — Approved; added to the `dev` dependency group.
- [x] 1.3 Decide whether the `Observation` log subsumes `FetchContext.diagnostics` or the two stay parallel. — Decided: stay parallel; subsuming touches the debug-envelope path for no Phase-1/2 benefit.
- [x] 1.4 Pin the full `Verdict` precedence ordering for `resolve_verdict`. — Pinned as the strict total order in `decision_log._verdict_rank` (not_found highest, ok lowest).

## 2. Phase 1 — Observation log + resolve_verdict (lossless verdict)

- [x] 2.1 Define the `Observation` frozen `dataclass(slots=True)` and the `(authoritative, verdict)` precedence model in `models.py` — module scope, no `dict[str, Any]` bag.
- [x] 2.2 Implement `resolve_verdict(log) -> Verdict` — pure, total, exhaustive `match` over `Verdict` closed with `assert_never`; the empty log is a defined case.
- [x] 2.3 Property tests for `resolve_verdict`: order-independence (`resolve(log) == resolve(shuffle(log))`), precedence-respecting, append-only monotonicity, idempotence, totality / never-invalid.
- [x] 2.4 Add the append-only observation log to `FetchContext`; remove the mutable `final_verdict` and `handler_not_found` fields.
- [x] 2.5 Make every tier-loop, gate, and escalation site in `fetcher.py` append an `Observation` instead of writing `final_verdict`.
- [x] 2.6 Delete `_phase_reconcile_verdict`; `build_response` derives the verdict via `resolve_verdict(log)`.
- [x] 2.7 Rewrite the `handler-verdict-precedence` tests as `resolve_verdict` precedence tests; add a characterization test asserting `FetchResponse` output is unchanged for representative fetches.
- [x] 2.8 `make check` green for Phase 1 — lint, `ty`, full suite, coverage ≥ 85%.

## 3. Phase 2 — Planner + pure-executor orchestrator

- [ ] 3.1 Define the `Action` vocabulary (`RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, `StopLiveTiers`, continue / no-op) in `actions/playbook.py`.
- [ ] 3.2 Implement `decide_next(log, caps) -> Action` as a totality-checked decision table; absorb `next_action_after_tier`, `next_action_after_gate`, and the gate's inline `suggested_tier == "browser"` routing.
- [ ] 3.3 Property / decision-table tests for `decide_next`: totality, and exactly-one-action for every combination of (resolved verdict × tier-exhaustion × browser budget × archive eligibility).
- [ ] 3.4 Rewrite the orchestrator tier loop and `_phase_gate_and_escalate` as a pure executor of `decide_next` actions — remove all inline escalation, rewrite, and stop policy.
- [ ] 3.5 Split `no_match`: in `SiteHandlerTier` / the `Handler` protocol, `no_match` is set only for unclaimed URLs; matched-but-failed handlers return real `Verdict` observations.
- [ ] 3.6 Thread the resolved cookie set through the `SiteHandlerTier` seam into `Handler.fetch`; the Reddit handler attaches cookies to its `httpx` client and classifies an HTTP-200 `{"error": 429}` / empty-listing body as `rate_limited`.
- [ ] 3.7 Make `build_response` a pure projection of the observation log; fold in `diagnostics` if 1.3 chose subsumption.
- [ ] 3.8 Update `tier-pipeline`, `quality-gate`, and `site-handlers` capability tests; re-run the characterization test — response output unchanged.
- [ ] 3.9 `make check` green for Phase 2 — lint, `ty`, full suite, coverage ≥ 85%.

## 4. Verify

- [ ] 4.1 Run `make bench` (live-network, spends LLM quota — user-gated) and record findings in `eval/findings_<date>.md`: this change moves tier routing and escalation, so a benchmark pass is warranted before considering it done.
