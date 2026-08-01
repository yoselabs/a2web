## Why

Two staleness defects and one dead knob, verified 2026-07-31. Each makes a2web
answer confidently from something it should not have trusted.

**1. Every handler-served response is cached for seven days.** `_ttl_for`
(`fetcher.py:263`) branches on one substring:

```python
if "html" in ct:
    return getattr(settings_obj, "cache_ttl_article_h", 24) * 3600
return getattr(settings_obj, "cache_ttl_static_h", 168) * 3600
```

"Static" was meant for assets. What actually lands in the `else` arm is every
API response a2web's own handlers produce — arXiv's `application/atom+xml`,
GitHub's `application/json`, Hacker News, Reddit. A question about a repo's open
issues can be answered from a week-old snapshot, and nothing in the envelope
says so. This is the most volatile content a2web serves, on its longest TTL.

**2. `cache_ttl_live_m` is declared in settings and referenced nowhere else.**
Grep across `src/` returns exactly one hit: the declaration at
`settings.py:106`. An operator who sets it gets silence — configuration that
reads as applied and is not. `is_live_only` exists but bypasses cache entirely
rather than consulting this value.

**3. Listing sufficiency is structurally off for every handler-served
listing.** `_phase_listing_completeness` returns at its first line when
`fc.record_count is None` (`fetcher.py:1459`), and `record_count` is set at
exactly one site — the DOM record-miner (`fetcher.py:1731`). A handler that
pre-renders its own listing never passes through it, so `listing_partial` cannot
fire. This is the measured cause of the 2026-07-28 bench failure where a2web
asserted completeness over a 25-item slice of a 445-entry arXiv listing and
scored 1 and 2 against WebFetch's 5. The handler half was fixed that day by
carrying the advertised total into the rendered markdown — **the answer was
fixed, the signal was not.** A machine consumer reading `operator_hints` still
cannot see the shortfall.

Additionally, `getattr(settings_obj, "cache_ttl_article_h", 24)` duplicates the
settings default as a second literal. Both keys exist today, so the fallback is
dead — but it is the shape that converts a settings rename into a silent
behaviour change instead of an error.

## What Changes

- **TTL is chosen from what the content IS, not from whether its content-type
  contains `html`.** Handler-served API responses get a short TTL appropriate to
  live data; genuinely static assets keep the long one.
- **`cache_ttl_live_m` is either wired up or deleted.** A declared setting that
  nothing reads is worse than an absent one.
- **`_ttl_for` reads settings directly** instead of through `getattr` with a
  duplicated default, so a renamed key fails loudly.
- **Listing sufficiency stops depending on the record-miner having run.**
  `record_count` gains a second writer: a handler that renders a listing already
  knows how many items it rendered and (via `listing_oracle`) how many the page
  advertises. The `listing_partial` hint fires on the handler path.
- **BREAKING (cache only):** existing cache entries written under the old TTL
  policy are not re-dated. Operators wanting the new policy applied to already-
  cached content must clear the cache; otherwise it drains naturally.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `cache`: TTL selection SHALL reflect content volatility rather than a
  content-type substring test; a declared cache setting SHALL be read by the
  code path it names.
- `listing-completeness`: the partial-listing signal SHALL be reachable on every
  path that produces a listing, not only the DOM record-miner path.

## Impact

- `src/a2web/fetcher.py` — `_ttl_for`, `_phase_listing_completeness`, the
  `record_count` writers
- `src/a2web/settings.py` — `cache_ttl_live_m`, and the TTL knobs generally
- `src/a2web/handlers/` — listing-rendering handlers gain a rendered/advertised
  count on the `TierResult`
- `src/a2web/cache.py` — no schema change expected
- `eval/corpus.yaml` — the arXiv listing case already exists and is the witness
- No dependency changes.

## Not Asserted

The BACKLOG records a `_MAX_RECORDS × DEFAULT_TOLERANCE` dead zone — a listing
truncated by a2web's own record cap reporting `ready` because the 0.9 tolerance
absorbs the shortfall. `DEFAULT_TOLERANCE = 0.9` is confirmed
(`content_expectations.py:31`), but **no `_MAX_RECORDS` constant was found in
`src/`**, so the interaction could not be verified and is deliberately left out
of scope. It needs locating in the shelf's `record_mine` before it can be
specified.
