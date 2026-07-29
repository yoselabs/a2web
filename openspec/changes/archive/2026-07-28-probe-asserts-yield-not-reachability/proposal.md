# Probe asserts yield over shapes, not reachability over one URL

## Why

`handler-parses-nothing-is-not-success` shipped a DOM parser and a verdict guard
for arXiv, and closed with one item open: wikipedia's yield has no structural
guard. Its `dom_schema` container is `<body>`, which always matches, so a rotted
selector reads as `EMPTY` rather than `ROT` and no verdict can be derived from
it. The captured-fixture test is the only thing holding it, and a fixture goes
stale the day the site changes.

The probe is the half that watches the live site. It cannot do that job today:

- It asserts **reachability**, not yield. `verdict == ok` and `content_md`
  non-empty. The arXiv handler passed this check for months while returning
  zero entries — a 40-char `## Papers (0)` body is non-empty.
- It probes **one URL per handler**, and for four handlers that URL is a detail
  page while the defect class lives on listings. arXiv was probed at
  `/abs/2308.08155`; the dead parser was on `/list/cs.CL/recent`.
- Three of its nine URLs are stale, so the probe is 3/9 red and has been read as
  "known red" rather than as a signal.

Measured while scoping this change, both by running the handlers:

```
site_handler:twitter   xcancel.com   status=200  verdict=ok   416 chars
  "# Checking your browser / Starting verification… / antibot[AT]xcancel[DOT]com"
```

The twitter handler reports **success on an anti-bot interstitial**. It clears
the current probe's non-empty check. `block_detector.evaluate` does not
fingerprint the page either — it falls through to a bare `length_floor`, so the
only thing separating this from a silent miss is that this particular
interstitial is shorter than the 500-char floor. That is the `length_floor`
laundering the wall catalogue's "bounded bespoke walls" comment already names.

```
site_handler:discourse meta.discourse.org/latest    verdict=ok  4237 chars  30 links
site_handler:discourse meta.discourse.org/t/…/1     verdict=ok  2650 chars   0 links
```

`linux.do` is unreachable from here, but the more interesting fact is that the
topic shape has never been probed at all.

## What Changes

- The probe declares, per handler AND per URL **shape**, what yield it expects:
  a content floor, a candidate floor, and the name of the property being
  checked. A handler that returns `ok` with a body below its floor, or with
  fewer candidates than it declares, fails.
- Every handler that populates `next_links` carries at least one case declaring
  a non-zero candidate floor. Enforced offline, so the declaration cannot
  silently drop to zero and read as green.
- Stale URLs refreshed: `linux.do` → `meta.discourse.org` (both shapes), nitter
  → the reachable instance. Reddit stays declared and stays failing — it is
  blocked from this network and an honest red beats a removed case.
- `block_detector` gains the anti-bot-interstitial fingerprint, with the
  captured page as its witness.
- Corpus entries for the four handlers that have none: `discourse`, `habr`,
  `twitter`, `v2ex`.

## Impact

- `src/a2web/handler_probe.py` — the case table and the assertions.
- `src/a2web/packages/block_detector.py` — one pattern.
- `tests/capabilities/site_handlers/` — the offline table guard.
- `tests/fixtures/captured/xcancel_antibot_interstitial.html` — the witness.
- `eval/corpus.yaml` — four entries.

Not in scope: fixing the twitter handler's verdict. The probe's job is to
surface it; the fix is a handler change with its own evidence. Named in BACKLOG.
