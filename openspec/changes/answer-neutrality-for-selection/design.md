## Context

Across this session a2web learned to be honest about a listing (partial signal),
to keep the whole shelf (rank-don't-skip options), and to hand back the judgable
dimensions (refinement axes). The one remaining overreach is the `answer` itself:
it still crowns a "best" by an arbitrary criterion, contradicting its own
bias hint. "Best" is criteria-less to a2web — criteria live with the caller. The
fix is to make the answer *present and relay* rather than *decide*, and to stop
welding the criteria (axes) to the completeness signal.

The economic frame matters: the scarce resource is the proxy fetch, not tokens.
An answer that drops on-page data forces a same-page re-ask to recover it — a
whole proxy round-trip for data already held. So exhaustive-first is the *cheap*
choice, and neutrality must never degrade into under-delivery.

## Goals / Non-Goals

**Goals:**
- `ask` answer is neutral on selection questions: no a2web-manufactured "best";
  criterion-disclosed leads only; source-stated preference relayed, attributed.
- `refinement_axes` (the criteria) surface on any listing selection question.
- Keep the lean single-fact path unchanged.
- Record the "shape & relay, never manufacture a selection" constitution invariant.

**Non-Goals:**
- Typed per-option source marker (relay in answer prose now; type it later if
  usage demands — the pin the user deliberately deferred).
- Structured exhaustive catalog for non-listing key-value sets (contact blocks
  the record detector skips) — future.
- Hard refusal to lead — ship the criterion-disclosed lead; tighten later if bench/
  usage says so.
- Any new wire field or tool-signature change.

## Decisions

**D1 — Criterion-disclosed lead, not hard refusal.**
The answer may still name a lead, but must (a) name the criterion, (b) frame it as
one lens, (c) never assert an unqualified "best". Rationale: preserves the genuine
quick-answer case ("just tell me, I trust you") while removing the false authority;
lower bench-regression risk than a hard refusal; reversible-tighter later.
*Alternative rejected:* hard "I won't pick" — philosophically pure but risks
under-serving the quick case and tanking answer-quality on decisive-answer corpus
items. Deferred as a possible tightening.

**D2 — Relay source preference in the answer prose, attributed.**
When the page marks its own preference/featured/default, the answer surfaces it as
the *source's* judgment ("the site marks X as preferred"), never as a2web's. Prose
relay works across every content shape (a 4-item contact block the record detector
skips, a 1123-row listing) with zero new plumbing. *Alternative rejected (deferred):*
a typed `source_marker` field — cleaner for programmatic callers, but freezes a wire
shape on a pin the user could not settle; revisit from real usage.

**D3 — Decouple criteria (axes) from partialness.**
`refinement_axes` are the judgable dimensions of the option set — needed by any
"which/best" question, complete or not. Change the gate from `items_loaded is not
None` (partial-only) to the listing kind (`routing.structural_form == "listing"`),
and broaden the prompt from "only when truncated/sorted" to "on any listing the
user is selecting/comparing over". *Alternative rejected:* keep partial-gating —
leaves a complete menu with no surfaced criteria, defeating the "best?" answer.

**D4 — Scope neutrality to selection questions.**
The neutrality + exhaustive behavior applies to selection/decision questions over a
set, not every ask. The model already classifies content (`structural_form`) and
reads the question; a single-fact ask stays lean. This protects the ~95%
single-fact path from bloat. The scoping lives in the prompt (the model recognizes
"pick from a set" vs "one fact").

## Risks / Trade-offs

- **[Bench answer-quality regression on decisive-answer corpus items]** → the
  criterion-disclosed lead (D1) keeps a usable lead, minimizing loss; `make bench`
  is the arbiter and the explicit "ship and measure" step. Tighten or loosen from
  data.
- **[Prompt drift on the locked router template]** → additions are in
  `tail_template` (non-cached); the `cache_prefix_template` stays byte-identical, so
  the v0.19 cache-prefix invariant holds.
- **[Neutrality read as laziness]** → guarded by the exhaustive floor: the answer
  must present the option space + relay source preference, not just decline. "No"
  without information is the failure mode, explicitly forbidden.
- **[Criteria surfacing on every listing adds output]** → axes are already an
  additive, omit-empty field; widening the gate surfaces them on complete listings
  too, which is the point (a "best?" over a complete menu needs criteria). Small,
  bounded (2-4 axes).

## Migration Plan

Behavioral (prompt) + a one-line gate change; no data migration, no wire-shape
change. Rollback = revert. Contract snapshot unaffected (no new fields). Run
`make bench` after landing and record findings — the neutrality change is
measured, not assumed.

## Open Questions

- Does the criterion-disclosed lead hold up on the bench, or does answer-quality
  push us toward either a hard refusal (tighter) or a fuller pick (looser)? Decide
  from bench + usage.
- When (if) to promote source preference from prose to a typed marker — driven by
  whether callers need to filter on it programmatically.
