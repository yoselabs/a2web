## Why

The `next_links` benchmark axis has scored **zero cells since ADR-0015 shipped**, and
nothing said so. ADR-0015 folded `next_links` into `other_pages` on the `AskResponse`
envelope; `runner._next_links_block` still reads `envelope["next_links"]`, gets `None`,
and `_score_next_links` returns early on the branch that means *"this system correctly
produced no block"*. Verified against the last full run
(`eval/runs/2026-07-22_024912/`): `next_links_score` is `None` on **29 of 29**
`a2web_extract` cells, while the stored envelope carries a populated `other_pages`
table. The report rendered `—`, which reads as *"axis not applicable to this corpus"*
and is the same glyph it would print if the axis were genuinely out of scope.

This is `close-silent-enforcement-loss` one layer out. That change fixed guards that
scanned nothing while reporting green; this is a *measurement* that scored nothing
while reporting a dash. The repo already carries the rule — "never add a structural
guard without an assertion that it found something" — and it was never extended across
the eval boundary, which is precisely where every near-miss of the 2026-07-27 session
landed.

The cost is not a wrong number, it is a **wrong decision**. The same run scored
`wikipedia-narrow-ask-indexes` at quality 2 on 2026-07-22; that finding was
rediscovered by hand five days later and reported as new. The measurement layer was
correct and on time. Nobody could tell it apart from noise.

## What Changes

- **Fix the dead axis at its root.** `_next_links_block` reads the field the envelope
  actually carries. The `query` envelope exposes `other_pages`; `fetch_raw` still
  exposes `next_links`. The reader resolves per system rather than assuming one name.
- **A skipped axis is distinguishable from an inapplicable one.** Every axis records a
  per-cell *disposition* — `scored`, `not_applicable` (the corpus entry does not ask
  for it), or `unscored` (it was asked for and no score was produced, with a reason).
  Today all three collapse into `None`.
- **Every reported statistic carries its denominator.** `quality` and `clarity` render
  a bare mean beside an `n` column counting all rows (`report.py:253-264`); `contract`
  and `next_links` already render `12/14` and `4.0 (8)`. The inconsistency is the tell
  that this is an absent rule, not an absent thought. All four axes render alike.
- **A run whose axis produced no scores at all fails loudly.** An axis asked for on
  ≥1 cell and scored on 0 is a broken harness, not a result. The run still completes
  and still writes its artifacts — a bench run is expensive and must never be thrown
  away — but the artifact and the exit path both say so.
- **A measurement run states its cache mode.** The extraction cache silently serves
  repeat cells, so "reproduced 4/4" can be one real sample. The manifest records
  whether the run bypassed the cache, and the harness offers an explicit bypass.
- **NOT in scope:** any change to what a2web returns, to `corpus.yaml`'s schema, or to
  what a case is expected to do. Expected-failure declaration (a corpus *vocabulary*
  gap, currently scoring correct ADR-0009 refusals as quality 0) needs somewhere to
  live before it can be expressed, and is deliberately sequenced after the corpus
  schema change. This proposal makes a run believable; it does not change what is run.

## Capabilities

### New Capabilities

- `eval-measurement-integrity`: a measurement states its own coverage. Every axis
  reports how many cells it scored and why it skipped the rest; a statistic is never
  rendered without its denominator; an axis that scored nothing while being asked for
  is a failure of the harness and is reported as one; and a run declares whether its
  observations were independent or cache-served.

### Modified Capabilities

- `output-benchmark`: the requirement "next_links candidate quality is scored on
  listing URLs" is currently unmet in production and its scenarios cannot detect that.
  It gains a scenario pinning the axis to the envelope field each system actually
  emits, so an envelope rename fails the axis loudly instead of silently voiding it.
  The "four axes per cell" requirement gains the disposition distinction.

## Impact

- `src/a2web/llm_eval/runner.py`: `_next_links_block` field resolution; the three
  silent `return` sites in `_score_next_links`; per-cell axis disposition on `EvalRow`.
- `src/a2web/llm_eval/report.py`: denominators on all four axes in `_write_axes`; a
  coverage section; the `—` glyph splits into distinct renderings.
- `src/a2web/llm_eval/__main__.py`: cache-mode flag and its manifest record.
- `tests/capabilities/output_benchmark/`: the four-axis harness tests gain the
  vacuity floor they currently lack — these run in `make check`, so the protection is
  enforced without spending quota.
- No production fetch/extraction path is touched. `make check` stays offline.
- Verification requires one full bench re-run (~8 min, subscription provider per
  ADR-0016) to confirm the axis reports real scores. That run is the change's evidence,
  not a side effect of it.
