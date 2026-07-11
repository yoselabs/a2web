## Why

The never-silently-miss floor (ADR-0009) is currently built as a **whitelist of specific verdicts** that earn the critical `try_user_browser` hint — and it's whack-a-mole. Three prior changes each bolted on another list:

- `_WALL_VERDICTS` = `block_page_detected` / `anti_bot` / `paywall` / `blank_page`
- `_is_escalatable_transport_wall` = `connection_error` / `timeout` / `rate_limited` / uncorroborated `not_found`

Anything not on a list falls through silently. Live testing found the hole: **`g2.com` ends `failed` with `length_floor` and NO hint, every run.** Its path is `raw 403 → jina returns a thin 200 → gate calls it length_floor`. `length_floor` is on neither list, so no hint. Worse, because jina "won" at the tier level, the resolved verdict becomes `length_floor` and the **earlier 403 is discarded** from the projection — so even the transport-wall list can't see the wall that started the cascade. Two separate holes, same silent miss: the caller is told a walled, content-rich page (g2's CRM category has 1,066 products, verified in a real browser) simply "failed," with no guidance.

The whitelist model guarantees this keeps happening — every new wall shape needs remembering to add it to a list, and one always slips.

## What Changes

**Invert the logic: blacklist the genuine "it truly isn't there" terminals; prescribe the browser on everything else that failed.** One floor, one rule:

> If a fetch ends `status: failed` and the resolved verdict is **not** a genuine-gone terminal, it SHALL carry the critical `try_user_browser` hint and `retrieval_incomplete: true`.

- **Genuine-gone terminals (the ONLY cases with no browser prescription):**
  - `dns_error` — the domain does not resolve; a browser can't conjure it → honest "doesn't exist", NOT `retrieval_incomplete`.
  - **authoritative** `not_found` — a site handler modelling the site's real "gone" semantics (deleted item); a browser won't un-delete it → NOT `retrieval_incomplete`.
  - `paid_auth_error` — keeps its own dedicated `paid_auth_error` hint (bad paid key, an operator error) instead of `try_user_browser`; still `retrieval_incomplete`.
  - `content_type_mismatch` — we DID retrieve a resource, it's just non-HTML (a PDF/image); a browser won't extract it better → no `try_user_browser` (see design open question).
- **Everything else that ends failed → `try_user_browser`:** the four content walls, the four transport verdicts, **and the ones falling through today** — `length_floor`, `proxy_unavailable`, `other`. `length_floor`-after-403 is covered by construction.
- **Single emission chokepoint:** delete the three scattered emission sites in `_phase_gate_and_escalate` and the two verdict whitelists (`_WALL_VERDICTS`, `_ESCALATABLE_TRANSPORT_VERDICTS` / `_is_escalatable_transport_wall`); replace with one systematic emission that runs once per fetch **after** the escalation phase, so the early-return at `fetcher.py:1668` can no longer split it into "transport path vs late path." `retrieval_incomplete` follows the hint automatically (the existing hint→incomplete hook), so it becomes systematic for free.

The `try_user_browser` message stays capability-generic (the spec forbids naming a product) — but it IS the prescription the caller acts on: a2web is the cheap fetcher; when it can't pass a wall, it tells the caller to escalate to its own real-browser tool (e.g. a native browser integration), which passes where all automation is blocked.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities

- `retrieval-completeness`: the never-silently-miss requirement is restated from a per-verdict whitelist to a **systematic floor** — any `failed` fetch that is not a genuine-gone terminal carries `try_user_browser` + `retrieval_incomplete`. The `blank_page` / transport-wall / content-wall scenarios collapse into instances of the one rule; `length_floor`-after-a-wall is newly covered.

## Impact

- `src/a2web/fetcher.py` — remove `_WALL_VERDICTS`, `_ESCALATABLE_TRANSPORT_VERDICTS`, `_is_escalatable_transport_wall`, and the three scattered `try_user_browser` emission blocks in `_phase_gate_and_escalate`. Add one `_prescribe_browser_on_wall(fc)` emission at the pipeline chokepoint (end of `_run_pipeline`, after `_phase_gate_and_escalate`) keyed on `resolved_verdict != ok and not _is_genuine_gone(fc)`. Keep the eager Reddit-handler hint + the `_has_browser_hint` dedup.
- `src/a2web/fetcher_response.py` — `retrieval_incomplete` derives from "failed + try_user_browser hint present" (existing hook) + `paid_auth_error`; the explicit wall-verdict tuple becomes redundant and is simplified. Genuine-gone terminals stay `failed` but NOT `retrieval_incomplete`.
- **Behavior change (intended):** more `failed` fetches now carry the hint — specifically `length_floor`, `proxy_unavailable`, `other`, and any future failed verdict. Existing tests asserting "failed verdict X carries no hint" for these must flip to expect the hint (legitimate expectation changes). Tests for the genuine-gone terminals (dns_error, authoritative not_found) must confirm they still carry NO `try_user_browser` and NOT `retrieval_incomplete`.
- No wire-shape change (same `operator_hints` / `retrieval_incomplete` fields); no tool-signature change; no new dependency.

Not in scope: the `blank_page` detection + hint (shipped, `escalate-on-thin-page-walls`); the transport-verdict escalation rules (shipped, `escalate-on-status-derived-walls`); making a2web itself drive a real browser (it prescribes the caller's, it does not embed one); `single-source-escalation-policy` (Finding 2, separate).
