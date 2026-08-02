# ADR-0018 — The generic layer is a floor, never a ceiling (product tenet)

**Status:** **Proposed** (drafted 2026-08-02)
**Date:** 2026-08-02
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (a silent miss is the cardinal harm — this is its shape one layer down), ADR-0012 (relay, never manufacture — the same refusal to substitute a2web's judgement for the source's), ADR-0015 (never withhold the body without leaving the index), inbox note `I0269`, findings `eval/findings_2026-08-02-schema-shaped-extraction.md` + `-entity-schema-spike-v1.md` + `-entity-schema-spike-v2.md`.

## Context

This rule has been discovered independently **four times**, paid for each time,
and written down nowhere as a rule:

1. **`_recipe_md`'s allowlist omitted `recipeInstructions`.** a2web served a
   recipe's ingredients and silently dropped how to cook them. Resolved
   2026-08-01 (`lift-the-item-set-and-renderer`) by demoting the allowlist to a
   label table that gates nothing.
2. **`_ENTITY_TYPES`** (`packages/structured_render.py:96`) is an eight-name
   schema.org allowlist. A `Person`, `JobPosting`, `Course`, or `Dataset` page
   renders as **nothing**.
3. **Four producer-claim losses in one week** — the `other_pages` fold rewriting
   every handler `kind` to `structural`; `_compose_next_links` deleting handler
   links the LLM did not repeat; `_run_extraction_escalation` replacing a site
   handler's whole index with the generic miner's; `_records_to_next_links`
   labelling every catalog row "source · discussed page". Each is already a
   `CLAUDE.md` **Never** entry, scoped to its own file.
4. **I0269 §5** — converging the six handlers' `next_links` derivation onto one
   shared function would replace six real site-specific `reason` strings
   (`142 points, 88 comments`) with the constant `"item page"`.

Each was fixed locally. None was named. A rule that exists only as four
incident-specific prohibitions cannot be applied to the fifth case before it
happens — which is exactly what I0269 asked for.

The rule is not novel. In protocol design it is the **must-ignore** principle
([RFC 6709](https://www.rfc-editor.org/rfc/rfc6709)), and RFC 6709 describes
a2web's own `_ENTITY_TYPES` mistake almost verbatim:

> a common mistake of inexperienced protocol implementers is to think that
> "MBZ" means it's their software's job to verify the value is zero on reception
> and reject the packet if not. This is a mistake, and such software will fail
> when it encounters future versions.

Substitute "not in `_ENTITY_TYPES`" for "not zero" and it is the same defect.

## Decision

**Every generic layer in a2web is a FLOOR under what it can express, never a
CEILING on it. A later stage may ADD to a producer's claim; it may never
silently replace, relabel, or drop it.**

Three obligations follow, and they are the checkable form of the rule:

1. **Unknown-but-present survives.** A value a2web does not recognise — a
   schema.org type outside any list it holds, a site-invented property
   (`discountPrice`, `couponCode`), a field a newer page shape introduced —
   passes through to the caller. a2web is an *intermediary* between the page and
   the agent, and an intermediary that drops what it does not understand
   silently narrows the web to a2web's vocabulary.

2. **A vocabulary a2web holds is a LABEL TABLE, never a GATE.** Lists exist to
   improve rendering (nicer labels, better ordering, promoted fields). The
   moment a list decides what is *kept*, it has become a ceiling. This is the
   `_recipe_md` resolution generalised.

3. **The producer's own claim outranks a later stage's reconstruction.** A site
   handler knows the site; a generic miner is guessing from shape. Where both
   speak, the later stage may append, never overwrite. Where the producer
   supplied nothing, a generic fallback is correct — and the test is
   **presence, not emptiness**: `reason if the producer supplied one else
   generic`, never `reason or generic`, because a producer that legitimately
   emits `""` would otherwise be silently overwritten.

### What this does NOT license

- **Not a licence to pass through unvalidated *structure*.** Closed-enum
  verdicts stay closed. The distinction is between a **verdict** (a2web's own
  judgement, where an unknown value means a2web is broken) and a **relayed
  observation** (what the page claims to be, where an unknown value means the
  web is bigger than our list). Only the second is open.
- **Not a licence to emit ungrounded content.** ADR-0014 still forbids URLs not
  on the page. "Preserve what the source said" and "invent nothing" are the same
  instinct, not opposed ones.
- **Not a licence to skip the quality gate.** A block page must still never
  enter cache.

## Evidence

The rule's cost was measured rather than assumed
(`eval/spikes/entity_schema_v2.py`, 24 paired rounds, subscription-only per
ADR-0016):

- Carrying an open `entity_type` + a pass-through `entity_fields` alongside the
  existing answer cost **no** measured answer content (adjacent recall
  `D − A` = −0.002, 95% CI [−0.046, +0.041]) and **no** correctness (core recall
  null on every contrast).
- **11 distinct type strings appeared across 8 pages**, including two that are
  not schema.org spellings (`Thread`, `ProgrammingLanguage`) and one near-miss
  (`DiscussionForumPost` vs `DiscussionForumPosting`). An eight-name allowlist —
  or any closed enum — would have been **wrong on this evidence**, not merely
  inflexible.
- **61-77 off-vocabulary properties survived** per arm (`arxivId`,
  `webmaster_email`, `pythonRequirement`, `firstStableRelease`). These are
  precisely what a fixed schema drops.
- The one thing that DID cost content was an instruction telling the model to
  keep `answer` short because the structured fields carried the facts
  (`C − D` = −52.8 chars, 95% CI [−83.9, −21.7]). **Economising is the harm; the
  extra vocabulary is not.** That is the rule stated as a measurement.

Cost, stated honestly: the entity block adds **~+132 completion tokens per call
(~+85%)**, which are not cached.

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

Per the ADR-0009 / 0012 / 0014 / 0015 precedent: a single project's product
invariant belongs in a2web's `CLAUDE.md` "Never" section with the rationale
here. `CONSTITUTION.md` is verbatim a2kit-synced substrate governance.

## Consequences

- `_ENTITY_TYPES` is demoted from a gate to a label table, or deleted. Pages
  typed `Person` / `JobPosting` / `Course` / `Dataset` stop rendering as nothing.
- Any future "which values do we accept here?" list must state, at its
  definition, whether it is a label table or a gate — and a gate needs a reason
  that survives this ADR.
- I0269 §5's `reason` / `anchor` carry becomes a forced move rather than a
  design debate: the producer supplied it, so it travels.
- The four scattered `CLAUDE.md` Never entries can cite one rule instead of
  four incidents.

## Re-evaluation triggers

- If pass-through is ever measured to cost answer quality (it was not, at
  n=24 on Haiku) — revisit obligation 1.
- If an open field is found being used as a routing key inside a2web, that is a
  closed enum wearing a string's clothes; either close it deliberately or remove
  the branch.
- If the token cost of carrying unknown fields becomes load-bearing at scale,
  the remedy is a cap on *volume*, never a return to an allowlist on *identity*.
