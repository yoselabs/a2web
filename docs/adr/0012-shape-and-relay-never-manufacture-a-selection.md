# ADR-0012 — a2web shapes & relays content; it never manufactures a selection (product tenet)

**Status:** **Accepted** (decided 2026-07-07)
**Date:** 2026-07-07
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never silently miss a URL — the sibling floor), openspec changes `content-aware-refinement-guidance`, `ask-retains-listing-options`, `answer-neutrality-for-selection`

## Context

a2web is a remote-first fetcher invoked by an AI agent that answers a human. A recurring temptation is for a2web to *decide for* the caller — to crown a "best" over a listing, to drop the non-winners, to filter or re-rank by a criterion of its own. This surfaced sharply on a shopping listing: asked "which crimping tool is best?", a2web crowned a winner by review count while its own hint said the sample was unrepresentative — and it deleted every other option off the wire. The premium/niche item (few reviews, lower crowd rating *by nature*) was exactly what got thrown away.

The owner's steer: **a2web has no criteria of its own.** "Best" is criteria-less to a fetcher — criteria belong to the caller (a shopping skill, the user), who alone knows "I'll pay premium" or "power matters more than price." a2web's job over a set is to *present it faithfully*, not to *pick from it*. But refusing to pick must never degrade into doing less: the scarce cost is the **proxy fetch**, so dropping on-page data forces a wasteful same-page re-ask to recover data already in hand.

## Decision

Elevate to a first-class a2web **product tenet**:

> **a2web shapes & relays content; it never manufactures a selection.** It may extract, structure, and preserve the page's own order; it may not rank, filter, hide, or crown by a criterion of its own.

Four pillars govern any question that asks a2web to pick from a set:

- **Exhaustive.** Bring the whole set, every option, every field. Declining to pick is NOT license to under-deliver. A thin selection answer is an unfinished job (this extends ADR-0009's floor from "never a silent miss" to "never a lazy under-delivery").
- **Faithful.** Relay the *source's own* judgment, attributed — a "preferred" contact, a "bestseller" badge, the page's default order. That is content, not a2web's verdict.
- **Neutral.** a2web adds no verdict of its own. It never crowns. It MAY offer a **criterion-disclosed lead** ("by rating, X leads — one lens"), never an unqualified "X is best".
- **One-shot.** Surface enough on the single fetch that the caller never re-asks the same page to reshape data already in hand. Never re-fetch for data you already hold; do re-fetch only for data you genuinely don't (a new slice — the caller's job).

The through-line of the whole content-completeness family: `listing_partial` (don't hide truncation), rank-don't-skip options (don't hide the losers), and this tenet (don't manufacture the pick) are one invariant — **a2web presents; the caller, who has criteria, decides.**

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

Per ADR-0009's precedent: this is a single product's behavioral invariant. It lives as a line in a2web's **`CLAUDE.md`** "Never" section, with rationale recorded here. It is **deliberately not** in `CONSTITUTION.md` — that is the verbatim a2kit-synced substrate governance, and a product tenet there would pollute shared governance and break the sync contract (Article V, Substrate Refusal).

## Consequences

- `ask`'s answer is neutral on selection questions: no manufactured "best", criterion-disclosed leads only, source-stated preference relayed attributed.
- `refinement_axes` (the judgable *criteria* of an option set) surface on any listing selection, decoupled from the completeness signal — criteria and partialness are orthogonal.
- The parsed option shelf (`ask` `options`) is retained page-order, never re-ranked by a2web.
- No new wire fields; a behavioral change validated by `make bench` (the neutrality change is measured, not assumed).

## Re-evaluation triggers

- If the bench shows the criterion-disclosed lead under- or over-serves, tighten to a hard refusal or loosen to a fuller pick — decide from data.
- If callers need to filter on source preference programmatically, promote it from answer prose to a typed per-option marker.
- If exhaustive-first is generalized to non-listing key-value sets (contact blocks the record detector skips), record the extension here.
