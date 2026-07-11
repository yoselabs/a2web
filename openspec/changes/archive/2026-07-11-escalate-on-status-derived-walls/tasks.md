## 1. Prerequisite check + grounding

- [x] 1.1 Confirm Step 0 status: has `http-fetch` shipped `FetchVerdict.dns_error` and has a2web adopted the bump + mapped it to a terminal `Verdict.dns_error` at `tiers/raw.py::_TRANSPORT_TO_DOMAIN`? If YES → implement the clean DNS carve-out (D3). If NO → implement the interim fallback (escalate all status-0 `connection_error`) and leave a one-line `# TODO(step-0)` guard to tighten. Record which path was taken.
- [x] 1.2 Verify `status_code` is present on every failure `tier_outcome` observation the rules will read (main tier-failure observe carries it; `proxy_unavailable` is status-0 by design). Confirm no failure path the rules key on omits it.
- [x] 1.3 Confirm the existing `_RULES` priorities and the `RulePriority` enum values so the new rules can be slotted at `LOW` below the gate-browser `HIGH` and correctly relative to the archive rules and `paid_last_resort`.

## 2. Add the transport/status escalation rules

- [x] 2.1 Add rule `forbidden_403_escalate` (connection_error + status==403 → EscalateBrowser, guard browser_dispatches<2), at LOW priority.
- [x] 2.2 Add rule `server_5xx_escalate` (connection_error + status>=500).
- [x] 2.3 Add rule `other_4xx_escalate` (connection_error + 400<=status<500, excl. 403; decide the 401/451 carve-out per design Open Question — default escalate, revisit if a real case shows a 401 should go straight to the terminal).
- [x] 2.4 Add rule `timeout_escalate` (Verdict.timeout).
- [x] 2.5 Add rule `network_drop_escalate` (connection_error + status==0 AND not dns_error per 1.1's path).
- [x] 2.6 Add rule `uncorroborated_404_escalate` (not_found + not authoritative). Confirm it does NOT preempt the existing Reddit-comment authoritative-archive path (authoritative not_found stays terminal / archive-routed).
- [x] 2.7 Add rule `exhausted_429_escalate` (rate_limited), generalizing beyond search/listing. Confirm interaction with the existing rate-limit handling in the reddit handler (its in-handler retry already ran; the planner rule fires on the surfaced rate_limited verdict).
- [x] 2.8 Ensure every rule guards `browser_dispatches < 2`, returns `EscalateBrowser` (never `EscalatePaid`), excludes `proxy_unavailable`, and is registered in `_RULES` at LOW with a unique name.

## 3. DNS terminal carve-out (Step 0-dependent)

- [x] 3.1 If Step 0 landed: add/confirm `Verdict.dns_error` mapping at the tier boundary and ensure `network_drop_escalate` excludes it; add a rule/branch that keeps `dns_error` terminal (no escalation). If interim: document the `# TODO(step-0)` and the bounded-waste behavior.
- [x] 3.2 Confirm authoritative `not_found` stays terminal (unchanged) and is excluded from `uncorroborated_404_escalate`.

## 4. Tests (behavior CHANGE — expectations widen, intentionally)

- [x] 4.1 Add a `decide_next` unit test per new rule (the rule-identity test-pair contract): each ambiguous verdict/status returns `EscalateBrowser`; each guard (browser cap, authoritative, dns_error, proxy_unavailable) returns `None`.
- [x] 4.2 Add an end-to-end `fetch()` test per class: a raw tier that returns 403 / 5xx / timeout / uncorroborated-404 now dispatches the browser tier (via the unified executor) rather than ending immediately; and on a persistent wall, proceeds browser → paid → the loud ADR-0009 terminal.
- [x] 4.3 Add end-to-end tests that the three terminal leaves do NOT escalate: `dns_error` (or interim: document), authoritative `not_found`, thin-2xx-no-fingerprint (already gated).
- [x] 4.4 Assert browser-before-paid ordering on a persistent transport wall (browser cap 2 spent → paid_last_resort fires → loud terminal), and that no rule spins past its cap.
- [x] 4.5 Update existing tests that asserted "transport failure X ends immediately / fails fast" to the new escalate-then-(maybe)-fail behavior. These are legitimate expectation changes (the whole point of the change), NOT contrived-fixture edits — verify each updated expectation reflects real desired behavior.

## 5. Verification

- [x] 5.1 Run `make check` (lint + ty + full test + coverage ≥85%) and `make arch`. Confirm `decide_next` stays pure/total, rule names unique, no `dict[str, Any]` bag, verdict remains the pure projection of the log.
- [x] 5.2 Update `playbook.py` docstring / rule-catalogue comments to describe the transport/status escalation rules and the DNS/authoritative-404 carve-outs.
- [x] 5.3 Sanity: one live `uv run a2web web fetch_raw` (or `ask`) against a known-403 host (e.g. the walled Reddit listing from this session) — confirm it now attempts browser escalation and ends with the loud terminal + critical hint rather than a bare failure. (Not `make bench` — no output-quality axis moved beyond reachability.)
  - VERIFIED 2026-07-11: live `fetch_raw` on `reddit.com/r/programming/top.json` → diagnostics chain `raw(403 connection_error) → browser → jina`; the 403 dispatched the browser rung mid-walk (was dead-ending at jina pre-Step-2). Terminal loud: `status=failed` + `retrieval_incomplete=true` + narrative + relayed block-page body.
  - CAVEAT / follow-up finding (pre-existing, NOT Step 2 scope): this URL degraded to a CONTENT wall (jina returned HTTP 200 with a block-page body → `block_page_detected`), not a transport verdict, so the machine-readable `try_user_browser` operator hint was absent. Cause: `_phase_gate_and_escalate` early-returns at fetcher.py:1668 when a wall arrives WITH a body, before the `_WALL_VERDICTS` hint at fetcher.py:1752 fires. Both lines predate this change (blame: 2026-05-22 / 2026-06-27). Step 2's transport terminal emits the hint correctly (e2e-tested). Track as its own change.
