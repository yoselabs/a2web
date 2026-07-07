## Why

`ask` still **manufactures a verdict** it has no basis for: on "which is best?"
it crowns a winner by an arbitrary criterion (review count) — while its own hint
says the sample is unrepresentative for a "best" judgment. That is a2web *making
a decision it cannot own*: "best" has no criteria a2web knows; criteria belong to
the caller (the shopping skill, the user). a2web has one job over a set — present
it faithfully — not pick from it.

The governing principle, crystallized across this session: **a2web shapes and
relays content; it never manufactures a selection.** Four pillars —

- **Exhaustive:** bring the whole set, every option, every field. Refusing to
  pick is not license to under-deliver.
- **Faithful:** relay the *source's own* judgment, attributed (a "preferred"
  contact, a "bestseller" badge, the page's default order) — that is content.
- **Neutral:** add no verdict of a2web's own; never crown.
- **One-shot:** surface enough on the single fetch that the caller never has to
  re-ask the same page to reshape data already in hand. The scarce cost is the
  **proxy fetch**, not output tokens — dropping data you already hold is the
  expensive choice, because recovering it costs a whole proxy round-trip.

## What Changes

- **Neutral answer on selection questions.** On a question that asks a2web to
  pick from a set, the `ask` answer SHALL NOT assert a2web's own unqualified
  "best". It MAY offer a **criterion-disclosed lead** ("by rating, X leads — one
  lens, not the answer") and SHALL **relay any source-stated preference**,
  attributed ("the site marks WhatsApp as preferred"). It presents the option
  space rather than deciding it. Single-fact asks ("the phone number?") are
  unchanged — this is scoped to selection/decision questions over a set.
- **Criteria decoupled from completeness.** `refinement_axes` (the judgable
  dimensions of the option set — the "criteria" a "best" would need) SHALL be
  surfaced on **any** listing selection question, not only truncated ones.
  Criteria and partialness are orthogonal; today they are welded (axes only fire
  when `items_loaded` is set).
- **Constitution invariant.** Record "a2web shapes & relays content; it never
  manufactures a selection" as a first-class rule (the through-line of
  listing-partial honesty, rank-don't-skip, and this change).
- **Non-goals (deferred, "see what we hit later"):** a *typed* per-option source
  marker (source preference is relayed in the answer prose for now, works across
  all content shapes); a structured exhaustive catalog for non-listing key-value
  sets (contact blocks the record detector skips); a hard refusal to lead (we
  ship the softer criterion-disclosed lead first and can tighten later).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ask-response`: the `ask` answer SHALL be neutral on selection questions — no
  a2web-manufactured "best", criterion-disclosed leads only, source-stated
  preference relayed attributed; and `refinement_axes` SHALL surface on any
  listing selection question, not only partial ones.

## Impact

- **Code**: `src/a2web/packages/llm_extract/prompts.py` (answer-neutrality +
  relay-source-preference instruction in `EXTRACT_ROUTER_V1`; ask criteria on any
  listing, not only truncated), `src/a2web/fetcher_response.py` (decouple the
  `refinement_axes` gate from `items_loaded` → gate on listing kind).
- **Wire contract**: no new fields, no tool-signature change — a behavioral
  change to the `answer` string on selection questions plus wider `refinement_axes`
  surfacing (already an additive, omit-empty field). Existing parsers unaffected.
- **Bench**: this moves answer behavior on "best/which" corpus items — a "best X"
  question that expected a decisive pick may score differently under a
  criterion-disclosed lead. `make bench` is the arbiter; run after landing and
  record findings. This is the deliberate "ship and measure" step.
- **Constitution**: adds an invariant (Phase A — human confirms the
  Constitution-touching edit).
