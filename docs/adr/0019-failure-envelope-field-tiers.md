# ADR-0019 — Failure-envelope field tiers: what an agent acts on vs operator debug noise

**Status:** **Accepted** (decision only — implementation is a follow-up bead, a2web-7bj.8)
**Date:** 2026-08-08
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never silently miss a URL — the axis `retrieval_incomplete` exists to serve), ADR-0017 (severity encodes confidence), inbox note `I0269` §5–6.

## Context

A single thin-200 failure in the I0269 session shipped six things that all
gesture at the same event:

```
status:               failed
tier:                  archive
retrieval_incomplete:  true
narrative:             "archive → length_floor:thin_fallthrough (2.5s)."
diagnostics_summary:   "tier=archive verdict=length_floor total_ms=2506 extras=thin_fallthrough"
operator_hints:        [{code: content_thin, message: "...", fix: "..."}]
```

Denis's question: which of these does an **agent caller** act on, and which
is operator debug noise that belongs behind `debug=True`? A sibling question
from the same session: does `headings` (a single entry, verbatim the first
`##` line of `content_md`) duplicate the attached body.

Both questions require *measuring what each field actually carries*, not
trimming on the principle that six fields sounds like a lot — ADR-0009's own
argument is that a floor must be **loud**, so cutting the wrong field would
quiet the miss signal it exists to prevent.

## What each field actually carries

Traced against `fetcher_response.py` (`build_response`, `_build_narrative`,
`_build_diagnostics_summary`) and `models.py` (`_WIRE_DEVIATION`,
`_FAILURE_ONLY_FIELDS`):

- **`status`** (`ok` | `failed`) — a coarse, lossy collapse of `final_verdict`
  (`length_floor`, `block_page_detected`, `paid_auth_error`, …) down to one
  bit. Deviation-only: dropped when `ok`.
- **`retrieval_incomplete`** (bool) — genuinely **orthogonal** to `status`,
  not derived from it. Traced through `fetcher_response.py:728-784`: it is
  seeded by `paid_auth_error`, then independently set by `ask_unanswered`, a
  requested render that failed, and a terminal classification lookup against
  `_INCOMPLETE_TERMINALS`. Critically, several `status: failed` outcomes
  **deliberately leave it `False`** — `gone_confirmed` (a corroborated dead
  URL is a confident fact, not a miss), `operator_error`, `unreachable` (both
  honestly terminal, carrying their own hints). So `status: failed +
  retrieval_incomplete: true` in the observed case is **not** one fact said
  twice — it is two independent axes (verdict vs. completeness) that happen
  to agree here. Collapsing them would silently lose the "failed but not a
  miss" state ADR-0009's own exclusions depend on.
- **`tier`** — which pipeline stage produced the result (`raw`, `archive`,
  `zyte`, …). Deviation-only: dropped when `raw` (the common case), so it is
  already free on the modal path. A coarse provenance/trust signal: an
  archive-tier result is a stale snapshot, a zyte/paid-tier result is a live
  fetch behind a harder wall — both are facts an agent may condition a retry
  or a trust judgement on.
- **`narrative`** — one prose line built from exactly four inputs:
  `tier_used`, `final_verdict`, `gate_subsystem`, `total_ms`
  (`_build_narrative`, `fetcher_response.py:350-362`). Already failure-only
  (`_FAILURE_ONLY_FIELDS`).
- **`diagnostics_summary`** — a `key=value` rendering of the **same four
  inputs** (`_build_diagnostics_summary`, `fetcher_response.py:366-381`):
  `tier=<tier_used> verdict=<final_verdict> total_ms=<total_ms>[
  extras=<gate_subsystem>]`. Already failure-only. This is the field the
  bd issue itself flagged as the candidate: it is a second serialization of
  `narrative`'s exact inputs, in a format built for grep/log parsing, not for
  an LLM-facing prose channel.
- **`operator_hints[].message`/`.fix`** — the one genuinely distinct, dense
  field: classification-specific, prescriptive text (e.g. `content_thin`'s
  "read the attached body to decide", `default_vhost_page`'s "the body is a
  placeholder, not the requested resource"). Not mechanically generated from
  `(tier, verdict, gate_subsystem, total_ms)` — it is the field an agent
  should actually read to decide what to do next.
- **`headings`** — **not** universally redundant with `content_md`, contrary
  to the surface reading of the observed case. `models.py`'s own field-tier
  docstring: `content_md` is dropped on a failed fetch, but `headings` is not
  gated by `_FAILURE_ONLY_FIELDS` — so on exactly the failure path this ADR
  is about, `headings` can be the **only** structural glimpse of the page the
  caller receives when the body itself is withheld. The observed duplication
  (a single heading verbatim matching the body's own `##` line) was a
  short-page edge case where the body WAS attached, not evidence of general
  waste. Cheap (a handful of short strings), no measured cost, real value in
  the failure case its sibling field can't cover — no cut proposed without
  actual usage measurement, which the bd issue itself asked to gate on.

## Decision

1. **`status`, `retrieval_incomplete`, `tier`, `operator_hints` stay exactly
   as they are** — each carries a fact none of the others do (verdict,
   completeness, provenance, and prescriptive action, respectively). None of
   these move behind `debug=True`; ADR-0009's floor stays loud.
2. **`diagnostics_summary` moves to the debug-only group.** It is a second,
   log-parseable serialization of `narrative`'s exact four inputs
   (`tier_used`, `final_verdict`, `gate_subsystem`, `total_ms`) — genuinely
   redundant for an agent caller who already has `narrative` (prose),
   `tier`/`status` (structured), and the hint (prescriptive). Its
   `key=value` shape signals its real audience: operator/log tooling, not an
   LLM-facing answer channel. It keeps existing exactly as-is for internal
   callers (the eval harness already reads it) and under `debug=True`.
3. **`narrative` stays failure-only, NOT debug-gated.** Unlike
   `diagnostics_summary`, it is the one human/agent-readable one-line
   summary of what happened, complementing (not duplicating in effect) the
   hint's prescriptive fix — narrative says what happened, the hint says
   what to do. Cheap (one line, failure-only already), keep as the default
   caller-visible summary.
4. **`headings` is unchanged.** No measured waste, real value on the
   content-withheld failure path, cheap regardless. Re-open only if a future
   measurement (not this ADR) shows genuine caller cost.

## Consequences

- A `debug=False` failure envelope drops one field (`diagnostics_summary`)
  relative to today; no other wire shape changes.
- `retrieval_incomplete` remains the single ADR-0009 completeness signal —
  this ADR explicitly rejects folding it into `status`, preserving the
  "failed but not a miss" states its own terminal exclusions depend on.
- Implementation (moving `diagnostics_summary` into the `debug` field group
  in `models.py`'s `_prune_wire` call, updating the fetch-response spec, and
  the regression tests) is **out of scope for this ADR** — tracked as a
  follow-up bead per the parent issue's acceptance criteria, since this
  repository's Ask-First list requires human confirmation before any
  response-envelope shape change lands.

## Rejected alternatives

- **Collapse `retrieval_incomplete` into `status`** (one field instead of
  two). Rejected: they are not redundant — several real terminal states are
  `status: failed` with `retrieval_incomplete: False`, and merging them would
  destroy that distinction silently, which is the exact class of harm
  ADR-0009 exists to prevent.
- **Drop `tier` to debug-only.** Rejected: it is already free on the modal
  (`raw`) path via deviation-pruning, and it is a legitimate coarse
  provenance signal (archive/stale vs. live-behind-a-wall) an agent may act
  on, not merely operator curiosity.
- **Cut `headings` when it duplicates `content_md`'s single heading.**
  Rejected without measurement: the general claim ("headings duplicates the
  body") is false on the failure path this whole ADR is about, where
  `content_md` is withheld and `headings` is the only structural signal
  left. The observed instance was a short-page edge case, not proof of
  systemic waste.
