# ADR-0009 — Never silently miss a URL (product tenet)

**Status:** **Accepted** (decided 2026-07-03)
**Date:** 2026-07-03
**Supersedes:** — (strengthens the existing `CLAUDE.md` "Never silently drop a fetch" line)
**Superseded by:** —
**Related:** ADR-0010 (Reddit reachability — where this tenet first bites), openspec change `reddit-reachability-never-silent-miss`

## Context

a2web is a remote-first fetcher invoked by an AI agent that then answers a human. The failure mode that matters most is not "a fetch failed loudly" — it is **a fetch that missed content but looks like it succeeded.** A hollow or low-confidence answer that the agent treats as complete means the human silently loses information and *does not know it.* You don't know what you don't know.

This surfaced concretely while working the Reddit reachability problem (ADR-0010): every walled path degraded down the tier ladder and could end in a low-signal result that a naive caller might present as an answer. The owner's steer: **a2web must never tolerate ANY unfetched URL being invisible.** An efficient power user driving an AI should be able to leverage *all* findings — and be told, explicitly and loudly, about the ones that could not be retrieved.

## Decision

Elevate to a first-class a2web **product tenet**:

> **Never tolerate ANY unfetched URL.** A URL a2web could not retrieve MUST surface as an explicit, critical, impossible-to-mistake-for-success failure — all the way to the human. Silent gaps are the disaster case.

Concretely, this tenet is enforced at the two places it can hold:

**a2web side (guaranteed):**
- A walled/unfetched URL returns `status: failed` + an explicit `retrieval_incomplete` envelope signal — never a soft low-confidence "answer" that reads as complete.
- The escalation hint (`try_user_browser`, see ADR-0010) carries `severity: critical` with imperative wording, not a polite suggestion.
- Bad credentials / service failures **report loudly**; a2web never silently substitutes a lower-quality path (this is the same tenet applied to keyed paid tiers).
- (Future) a `doctor`-style coverage surface makes "what a2web could not reach, and why" visible rather than buried.

**Caller side (made hard to ignore):** the hint commands rather than suggests — `retrieval_incomplete` + `status: failed` + `critical` severity + imperative text mean that ignoring the gap requires active negligence. a2web cannot *force* the downstream agent to obey, but it guarantees the miss is unmissable in the envelope.

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

The tenet lives as a strengthened line in a2web's **`CLAUDE.md`** "Never" section (its natural sibling: "Never silently drop a fetch — `status: failed` + populated `diagnostics` + `narrative` + `operator_hints` is the floor"), with rationale recorded here.

It is **deliberately not** placed in `CONSTITUTION.md`. The Constitution is a verbatim copy synced from a2kit that governs *how decisions are made* across the whole ecosystem (substrate/product placement, dependency adoption, magic budget). A single product's behavioral invariant would pollute shared governance and break the a2kit sync contract ("drift is a bug"). Product tenets belong in the product; the Constitution stays about meta-rules.

## Consequences

- Additive envelope fields: `retrieval_incomplete` (bool) and `OperatorHint.severity` (`info`/`critical`, default `info` — backward-compatible).
- Parsers ignoring unknown fields are unaffected, but SHOULD begin honoring `retrieval_incomplete`.
- This tenet retroactively justifies several ADR-0010 decisions: dropping PullPush (stale = silent miss), fail-loud-on-bad-key (no silent downgrade), and escalating walls instead of returning hollow answers.

## Re-evaluation triggers

- If a `doctor`/coverage surface is built, update this ADR to cite it as the third enforcement mechanism.
- If a machine-readable per-field insufficiency signal is ever added (see ADR-0006's declined `answerable: false`), reconcile the two.
