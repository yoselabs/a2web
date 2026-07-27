# Fix the extraction contract's signals: saturated, coarse, and lossy

## Why

Three defects in how the `query` extraction path reports on itself. They were
found together because each was hiding the next.

**1. `llm_wobble` is saturated — it is not a signal.** A completely healthy,
fully-recovered extraction emits **five** `llm_wobble` warnings, one per
legitimately-omitted optional field (`obstacle`, `also_here`, `other_pages`,
`refinement_axes`, `item_total_seen`). Measured, not inferred: a canned
fenced envelope carrying only `answer`/`structural_form`/`shape` produces five
events and `routing is not None`. The tolerance vocabulary conflates two
different facts — *"the field was absent, which is normal for an optional
field"* and *"the field was present but malformed, so a default was
substituted"*. Only the second is a wobble. A log key that fires on 100% of
healthy calls cannot be used to detect anything, which is why it was about to
be adopted as the measurement channel for a production rollout.

**2. `routing_lost` is a bool over three unlike events.** `routing_payload is
None` collapses: an envelope that never parsed; an envelope that parsed with
`answer` intact but no classification; and a provider that threw (already
reported separately via `provider_error`). The three have different causes,
different consequences, and — critically — different correct responses. The
conflation is what made the earlier "index lost" attempt look unshippable.

**3. Missing classification silently discards a supplied index.** In
`_build_router_payload`, a missing or non-string `structural_form`/`shape`
returns `payload=None` **before** `also_here` / `other_pages` are ever parsed.
A model that supplies a perfectly good index but omits the classification has
that index thrown away with it. Only the options-shelf gate needs the
classification; the index does not. This is a correctness bug independent of
how often it fires.

### What this change deliberately does NOT do

An earlier draft promoted routing loss to `status: failed` +
`retrieval_incomplete: true`. That is dropped, on two independent grounds.

*Principle:* `failed` + `retrieval_incomplete` is the signal that steers callers
toward `try_user_browser` and re-fetching. It would prescribe browser escalation
for a page a2web fetched perfectly, to repair an LLM formatting artifact that a
re-fetch cannot touch. Status describes retrieval; hints describe extraction
degradation. The only extraction event that earns `failed` is *no answer*, and
`ask_unanswered` already owns it.

*Evidence:* two live spikes (15 extractions, subscription provider) recovered
the routing payload **15/15**, including the exact `bhklima.com` 404 that
motivated the original bug report, and including a deliberately degenerate set
of 404s and thin pages chosen to falsify the hypothesis that unparsable
correlates with degenerate pages. It did not. The `unparsable` population was
largely *created* by the double-contract defect fixed in `bc52b4c`, and largely
*deleted* with it. Building failure promotion, a retry rung, and an
`include_content`-conditional status for that population would be machinery for
a near-empty case.

A retry rung is also dropped: its stated economic justification (that failing
forces the caller to pay a fresh proxy fetch) is false — `_phase_cache_check`
serves a same-URL re-query from the HTTP cache within TTL, so the rung buys
latency, not proxy budget.

## What Changes

- **Split the tolerance vocabulary** so an absent optional field is not reported
  as a wobble, restoring `llm_wobble` to a signal that means something. Shelf
  `llm-wobble` EVOLVE (additive), adopted back here.
- **Replace `routing_lost: bool`** with a typed `RoutingOutcome`. The bool is
  deleted, not deprecated — no parallel field, no compatibility shim.
- **Decouple the index from the classification**: a missing `structural_form` /
  `shape` salvages `also_here` / `other_pages` and suppresses only the
  options shelf.
- **One `warning` operator hint** when the index is genuinely lost, naming the
  cheap recovery explicitly (`fetch_raw` on the same URL is cache-served). This
  closes ADR-0015's "never *silently*" clause. It will fire rarely — which is
  the point; a rare warning is a signal, a constant one is noise.
- No status changes. No retry. No `include_content` conditional.

## Impact

- Affected specs: `extraction-contract`, `observability`
- Affected code: `packages/llm_extract/extractor.py`,
  `packages/llm_extract/wobble/_policies.py`, `fetcher.py`,
  `fetcher_response.py`, shelf `llm-wobble`
- **Wire**: adds one conditional operator hint; `also_here`/`other_pages` now
  survive a classification miss. Goldens move deliberately, via
  `make bless-wire SLUG=extraction-signal-fidelity`.
- **Risk**: low. The hint is additive and rare; the decoupling can only add
  index entries that the model already supplied; the tolerance split only
  removes log lines that fire on healthy calls.
