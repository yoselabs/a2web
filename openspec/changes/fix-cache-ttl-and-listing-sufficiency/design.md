## Context

Three defects that all end in a2web presenting something as current or complete
when it is neither. Verified 2026-07-31 by reading the call sites and grepping
for readers.

The listing half has documented history: `eval/findings_2026-07-28-full.md`
records the bench cell where a2web answered *"you are seeing all 25"* about a
445-entry arXiv listing, scored 1 and 2 against WebFetch's 5, and traced the
cause to this exact gate. That session fixed the handler's rendered markdown and
explicitly recorded that the SIGNAL remained broken. This change closes it.

## Goals / Non-Goals

**Goals**

- Live data stops being cached as if it were an asset.
- No declared cache setting is unread.
- `listing_partial` fires on the handler path.

**Non-Goals**

- Reworking the cache schema or the `(url, profile_hash)` key.
- The `_MAX_RECORDS × DEFAULT_TOLERANCE` interaction — not verified, explicitly
  out of scope (see the proposal's "Not Asserted").
- Making `extract_records` recognise `<dl>/<dt>/<dd>`. That is the shelf-side
  half of the 2026-07-28 finding and remains a separate promotion. **This change
  deliberately routes around it** rather than waiting on it: the handler already
  knows its own counts, so sufficiency does not need the record-miner to work.

## Decisions

### D1 — Volatility is a property the producer declares, not one the cache infers

The current test infers volatility from a content-type substring and gets it
backwards for every handler. Replacing it with a longer substring table would
repeat the mistake with more branches.

Instead the producer declares it. A `TierResult` already carries typed fields;
handlers know whether they served an upstream API response. The cache reads the
declaration and falls back to the content-type heuristic only where nothing
declared — which after this change means the generic HTTP tiers, where the
heuristic is actually appropriate.

This mirrors `wire._TSV_FIELDS`: the thing that is a contract is stated, not
inferred.

### D2 — `cache_ttl_live_m` gets wired up, not deleted

It names a real concept a2web already half-implements: `is_live_only` bypasses
cache entirely for live-only URLs. A five-minute TTL is the softer, more useful
form of the same idea, and it is the natural default for D1's handler-declared
live data.

If wiring it up proves to duplicate `is_live_only` exactly, delete it instead —
but decide by looking, not by leaving it declared.

### D3 — `record_count` gains a second writer rather than a parallel gate

The temptation is a separate handler-listing sufficiency path. That would give
two implementations of one question, which is how the response contract ended up
in three files.

Instead: a handler rendering a listing populates the rendered count and the
advertised total on its `TierResult`, and the orchestrator writes them to the
same `record_count` / oracle inputs the miner path writes. One assessment, two
sources.

`arxiv.py` already computes both — `_render_listing` takes `advertised_total`
from `listing_oracle` and renders `Papers (25 of 445)`. The values exist and are
discarded; this change stops discarding them.

### D4 — The prose/hint agreement scenario is the anti-drift clause

Requiring that the rendered prose and the emitted hint carry the SAME counts
prevents the exact state this change is fixing: one half correct, the other half
absent, with nothing failing.

## Risks / Trade-offs

- **Shortening handler TTLs increases upstream traffic.** That is the point —
  the current TTL is serving week-old issue lists — but it is a real cost against
  rate-limited APIs (GitHub unauthenticated is 60/hr). The short TTL should be
  set with that limit in mind, and `A2WEB_GITHUB_TOKEN` becomes more valuable.
- **Existing cache entries keep their old TTL.** Not re-dating them avoids a
  migration; the cost is that the old policy drains over up to seven days.
  Documented in the proposal as the one breaking note.
- **A handler-declared volatility field is one more `TierResult` field**, on a
  type already carrying 25. Justified because the alternative is inference, and
  because T5/T7 already have `TierResult`'s width on their list — this change
  should not be blocked on that cleanup.

## Open Questions

- What short TTL? Long enough to make a re-query cheap (the ADR-0015 `also_here`
  path assumes a cache-served same-URL re-query), short enough that an issue list
  is current. Five minutes matches `cache_ttl_live_m` and the extraction cache's
  15-minute sibling; measure the `also_here` re-query window before fixing it.
- Should a cache HIT on stale-but-valid content carry a hint naming its age?
  Arguably yes under ADR-0009 — but it is a wire change and belongs in its own
  decision, not smuggled in here.
