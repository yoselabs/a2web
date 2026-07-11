## 1. Map the current state (no code changes)

- [x] 1.1 Grep-audit every reference to the two executors and their coupling: `_execute_tier_action`, the `_Exec` enum (RESTART/STOP/CONTINUE), the post-gate `while True` loop in `_phase_gate_and_escalate`, `render_requested`, `escalate_to_render`, `_phase_obstacle_render`, `_phase_listing_render`. Record every call site and reader so nothing is orphaned by the collapse.
- [x] 1.2 Confirm the current `Action` union members and which executor handles each today; confirm the browser cap (2, fast→robust) and paid cap (1) enforcement points in `playbook.py`. Note the exact `_run_pipeline` ordering relative to `_phase_cache_write` (the pre-cache render invariant). Establish a green baseline on the affected suites before any edit.

## 2. Build the single unified executor

- [x] 2.1 Replace `_execute_tier_action` with `_dispatch_action(fc, action, *, state, post_gate) -> _Exec` handling the FULL `Action` union (`RewriteUrl`, `RetryViaArchive`, `EscalateBrowser`, `EscalatePaid`, `Continue`) in one place.
- [x] 2.2 Model `RewriteUrl` (tier-walk restart) as a first-class `_Exec.RESTART` control outcome so the tier-loop restart and post-gate escalation share the one mechanism (design D2). Preserve the 1-rewrite cap.
- [x] 2.3 Represent the one genuine pipeline-region divergence honestly via the `post_gate` parameter (design D6): tier-walk archive installs the body only (`_install_archive_payload`, STOP); post-gate archive installs extracted fields + regates (`_install_gate_archive` + `_regate_after_escalation`, CONTINUE).
- [x] 2.4 Route the tier-loop after-tier dispatch through `_dispatch_action(post_gate=False)`; move the won-tier install to the tier-loop call site (keyed on the tier result, not a planner `Action`), preserving the exact archive-fail → tier-win → advance semantics.
- [x] 2.5 Route the post-gate escalation loop through `_dispatch_action(post_gate=True)`, acting only on the three escalation actions and breaking on Continue / (never-in-practice) RewriteUrl — matching the prior `else: break` exactly.

## 3. Tests + verification

- [x] 3.1 Add a test asserting `_dispatch_action` dispatches every `Action` type (`RewriteUrl` → RESTART; `RetryViaArchive` → install variant per `post_gate`; `EscalateBrowser`; `EscalatePaid`; `Continue` → no-op) — no action is a silent no-op where the planner can legally return it.
- [x] 3.2 Add a test asserting `RewriteUrl` from the planner restarts the tier walk exactly as today, with the 1-rewrite cap preserved (e.g. the arxiv PDF → abs rewrite path).
- [x] 3.3 Run the affected suites and confirm green with NO expectation edits that change observable output: `tests/capabilities/cascade_decision_log/`, `tests/capabilities/quality_gate/`, `tests/capabilities/listing_completeness/`, `tests/capabilities/tier_pipeline/`, `tests/capabilities/fetch_response/`, `tests/capabilities/ask_response/`.
- [x] 3.4 Run `make check` (lint + ty + full test + coverage ≥85%) and `make arch` (architecture invariants). Confirm no `dict[str, Any]` bag, no mutable verdict slot, tools still return pydantic not str, verdict remains the pure projection of the log.
- [x] 3.5 Update `_dispatch_action` / tier-loop / post-gate docstrings so they describe one executor + the `post_gate` divergence accurately; leave `playbook.py` docstring's "single escalation-policy function" claim honest by noting the completeness-escalation phases are a documented follow-up (Finding 2), not yet folded.

## 4. Follow-up (NOT this change — recorded for the next change)

- [ ] 4.1 (follow-up `single-source-escalation-policy`) Fold `_phase_obstacle_render`, `_phase_listing_render`, and the `render_requested` / `escalate_to_render` ladder into planner rules; design the `EscalatePaid(scroll=…)` Action variant + the post-render re-extraction step. Tracked separately; left here as a pointer only.
