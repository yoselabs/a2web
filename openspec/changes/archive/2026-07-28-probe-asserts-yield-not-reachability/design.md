## Context

The probe exists because unit tests monkeypatch the transport and cannot see a
live regression. It has a second blind spot of the same shape: it monkeypatches
nothing, but it asserts so little that a dead parser passes it.

```
                    what the probe checks        what rots
  reachability      ✓ verdict == ok              transport, DNS, cert
                    ✓ content_md non-empty       a total handler failure
  ────────────────────────────────────────────────────────────────────
  yield             ✗ entry count                SELECTORS  ← the gap
                    ✗ candidate count            the index
  shape coverage    ✗ one URL per handler        listing-only parsers
```

arXiv sat in the bottom-right cell: a listing parser, never probed on a listing,
asserted only for non-emptiness. Wikipedia is in it now, and unlike arXiv it
cannot be pulled out by a verdict guard.

## Goals / Non-Goals

**Goals**

- A handler whose parse rots fails the probe rather than passing it.
- Every shape a handler claims to serve is exercised at least once.
- What each case checks is written down, so a weak assertion is visibly
  deliberate rather than accidentally absent.

**Non-Goals**

- Making the probe green. It is 3/9 red today and this change does not promise
  9/9 — reddit is blocked from this network. See D4.
- Fixing the twitter handler's `ok`-on-a-wall verdict. Surfacing it is this
  change; fixing it is a handler change.
- Putting the probe in `make check`. It is live-network and stays out.

## Decisions

### D1 — Declared yield per case, not a global rule

Each case declares its own floors:

```python
ProbeCase(
    url="https://arxiv.org/list/cs.CL/recent",
    shape="listing",
    min_chars=1000,
    min_candidates=5,
    checks="dt/dd entries parsed into drilldown candidates",
)
```

A global rule ("every handler must yield 5 candidates") is wrong in both
directions: habr and v2ex are article handlers with no index, and a floor of
zero applied globally is the check that already failed. Per-case floors let the
strong assertion be strong where it is available.

`checks` is prose and is REQUIRED. The change spec says a weaker assertion must
record what it checked, so a later reader can tell a deliberate weaker
assertion from an overlooked one. A field nobody has to fill would not do that.

The floors are set below the observed value, not at it. `min_chars=1000` against
an observed 4971 catches a collapse to `## Papers (0)` without failing on a
quiet day when arXiv lists fewer papers. A floor pinned at the observed value
would be a golden, and would fail on content rotation rather than on rot.

### D2 — Shapes are per-handler cases, not a second table

A handler's shapes are simply multiple entries in its case list:

```python
"site_handler:discourse": (
    ProbeCase(".../latest",          shape="listing", min_candidates=10, …),
    ProbeCase(".../t/new-to-…/1",    shape="detail",  min_candidates=0,  …),
)
```

This keeps the loud-failure property that already exists — a registered handler
missing from the table fails the probe — and extends it without a second
structure to keep in sync.

### D3 — The candidate floor is guarded offline

The probe is live-network and not in `make check`, so nothing stops the floors
from being edited down to zero to make a red probe green. That is the exact move
that produced the defect this change is about: an assertion weakened until it
could not fail.

So an offline test asserts the SHAPE of the table: every handler whose module
populates `next_links` has at least one case with `min_candidates > 0`.
"Populates `next_links`" is read from the source by AST — a `next_links=` keyword
argument in the handler module — rather than from a list, because a list is the
thing that goes stale.

This is deliberately a weaker claim than "the floor is right". It cannot check a
number against a live site from an offline suite. What it can check is that the
number was not deleted, and that is what happened last time.

Non-vacuity: the test asserts it found at least 6 handlers and at least 5
next_links-populating ones, per the standing rule that a guard reporting
"0 violations in 0 candidates" reads as coverage while providing none.

### D4 — Reddit stays declared and stays red

Reddit is blocked from this network without a proxy: the detail URL returns
`not_found`, the listing `block_page_detected`. Both were measured.

The tempting move is to drop the case or lower its floor so the probe reports
green. Both convert a known-blocked handler into a silently unprobed one, which
is the failure mode of the whole change. The case stays, declares real floors,
and fails. The probe's output names it.

A probe that is honestly 8/10 is more useful than one that is dishonestly 10/10,
and this is the same argument the empty-vs-wall invariant makes about a
false-positive empty: over-warning is cheap, a confident miss is not.

### D5 — The wall fingerprint ships with the captured page

`block_detector`'s catalogue is explicitly a bounded list of bespoke walls that
would otherwise launder into `length_floor`. The xcancel interstitial is one:

```
# Checking your browser
Starting verification…
… antibot[AT]xcancel[DOT]com … reference ID: no_id_generated
```

`Checking your browser` is Cloudflare's classic IUAM title and is at least as
tight as the markers already in the catalogue (`Just a moment`,
`Attention Required`). It ships with the captured 6822-byte page as its witness,
not a hand-written approximation — the rule this repo adopted three days ago.

What this does NOT do is fix the twitter handler. The handler still returns
`Verdict.ok`; the fingerprint means the GATE now calls the page a wall instead
of thin, which is the difference between a loud `try_user_browser` and a hedged
"possibly empty". The handler-side fix is a separate change with its own
evidence.

**And it does not close the case that motivated it.** `_BLOCK_PATTERNS` is
consulted only below `LENGTH_FLOOR`. This interstitial renders to 416
characters, so it is caught; an interstitial from the same family that rendered
past 500 would not be, and would still read as content. The draft of this
decision presented that as the risk the fingerprint removes, which is backwards
— it is the risk that survives it.

Making the marker length-independent (as turnstile, Akamai and Baxia are) would
close it and is the wrong trade here: those markers are asset paths and widget
ids that cannot plausibly appear in prose, whereas "checking your browser" is an
English sentence that a page ABOUT anti-bot systems would contain. A
false-positive wall on a legitimate article is the failure the catalogue's
"tight markers" rule exists to prevent. The residual gap is real, bounded, and
belongs to whoever finds a wordier instance in the wild.

## Risks / Trade-offs

- **A floor set too high makes the probe flaky.** Mitigated by setting floors
  well below observed values (D1), but a site that genuinely shrinks its
  listings will fail the probe. That is the intended direction of error.
- **`Checking your browser` could false-positive** on an article about
  anti-bot systems. The catalogue's standing rule is tight markers from observed
  block pages, and this is one. Precedent markers carry the same exposure.
- **The AST read of `next_links=` is a heuristic.** A handler could populate
  candidates through a variable and be missed. That is a false negative in a
  guard, not a false positive — it under-enforces rather than blocking correct
  code, and the probe's own loud-failure check still catches a handler absent
  from the table entirely.
- **The probe stays red.** Anyone reading exit status alone learns nothing new.
  The value is in the per-case lines, which now say what was expected.

## Open Questions

- **Should the probe run on a schedule?** A live check nobody runs is a live
  check that reports the state of the world on the day someone remembered. Out
  of scope; noted.
- **Does the twitter handler have any reachable upstream?** All three nitter
  instances tried are dead or walled. The handler may be dead code with a live
  test. Not decided here.
