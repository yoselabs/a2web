# The bench's noise floor, measured

Two full bench runs, ~30 minutes apart, against a **byte-identical `src/` tree**
(`git diff --name-only c795f94..HEAD -- src/` → empty). Same 42 corpus entries,
same three systems, provider `claude-code-sdk` (ADR-0016).

- run 1 — `eval/runs/2026-08-01_145329/`
- run 2 — `eval/runs/2026-08-01_152218/`

Purpose: the harness could not say what a ±X move means, so every claim of the
form *"this change improved quality by 0.2"* was unfalsifiable in both
directions. This run pair is the missing denominator.

## The headline number

| system | quality | clarity | env tokens |
|---|---|---|---|
| webfetch_baseline | 2.02 → 1.95 (**0.07**) | 3.36 → 3.40 (**0.04**) | 220 → 209 |
| a2web_detail | 3.17 → 3.34 (**0.17**) | 1.36 → 1.36 (**0.00**) | 4445 → 4829 |
| a2web_extract | 3.38 → 3.29 (**0.09**) | 3.76 → 3.95 (**0.19**) | 732 → 795 |

**System-mean noise floor: ±0.2 on quality, ±0.2 on clarity, with nothing
changed.** `next_links` (3.11/3.00) and contract (42/42) were stable across the
pair.

### What this retroactively says about today's earlier claims

`findings_2026-08-01-pm.md` reported `a2web_extract` quality 3.52 → 3.33 (0.19)
and `a2web_detail` 3.27 → 3.40 (0.13) across the renderer lift, and declined to
read either as a result. That was the right call and is now quantified: **both
moves are inside the floor.** They were not small real effects; they were not
effects.

## The mean hides the real behaviour

Per-cell, matching on `(slug, system)`:

| axis | cells | identical | mean abs Δ | p90 | max |
|---|---|---|---|---|---|
| quality | 124 | 102 | 0.30 | 1.00 | **5.00** |
| clarity | 102 | 64 | 0.57 | 2.00 | **5.00** |

Most cells are perfectly stable. A minority swing the full width of the scale,
and the system mean is calm only because 42 cells average them out. **Twenty-one
cells moved ≥2 points on an unchanged tree.**

So the two levels need different thresholds, and conflating them is the trap:

```
   SYSTEM MEAN            n=42, averages the swings out
      ±0.2  ────────────  usable, with care

   SINGLE CELL            one adversarial page, one judge call
      ±5.0  ────────────  not a measurement at all
```

A per-slug claim ("this change fixed `g2-crm-wall`") is currently worth nothing
without repeats. The bench answers *"did the system move"*, never *"did this page
get better"*.

## The mechanism is retrieval luck, not judge mood

The big swings are not spread evenly — they cluster on **walled and adversarial
pages**: `walled-page-with-preceding-info-hint`, `g2-crm-wall`,
`reddit-iem-compare`, `trendyol-listing-which-best`. Traced one to the bottom:

| | run 1 | run 2 |
|---|---|---|
| status | `failed` | `ok` |
| tier | `jina` (verdict `length_floor`) | `archive` |
| **quality** | **5** | **1** |
| **clarity** | **0** | **5** |

The live site walled us in both runs. In run 1 nothing got through and a2web
correctly reported the wall; in run 2 the Wayback lookup happened to hit. So the
cell is measuring **whether an archive snapshot was reachable at that minute** —
a property of the internet, not of this repository.

Two consequences worth separating:

1. **The axes point in opposite directions on the same cell.** The honest
   failure scores quality **5** (it satisfies ADR-0009: the wall is declared,
   nothing is laundered into a confident answer) and clarity **0**. The archive
   success scores quality **1** (the answer is stale) and clarity **5**. Both
   judgements look defensible in isolation. Together they mean the cell's score
   is decided by a coin flip, and any change touching wall handling or archive
   dispatch will show quality movement that is confounded with retrieval luck.

2. **The quality-1 on the archive branch is arguably the judge being right.** An
   answer reconstructed from an old snapshot IS worse than an honest miss for
   these questions. That is the same concern the `archive_snapshot_age` hint
   shipped for earlier today — and it suggests the hint is treating a real
   problem, independently observed by a judge that knows nothing about it.

## What to do with this

Recorded rather than acted on, because the fix is a corpus decision:

- **Quote system means, never single cells**, and only past ±0.2.
- **A run pair should be the unit**, not a run. One run against an unchanged
  tree costs ~30 min of subscription quota; the denominator is cheap relative to
  being wrong about a regression.
- **The adversarial slugs need a decision.** Either their criteria should score
  the *envelope's honesty* (which is deterministic and is what ADR-0009 actually
  requires) rather than the answer's content (which depends on whether the fetch
  landed), or they should be pinned to captured pages. Today they are the noisiest
  cells in the corpus and they are measuring the network.
- **This pair is not the whole floor.** Runs 30 minutes apart share the day's
  page content. The control arm — `webfetch_baseline`, which no a2web change can
  affect — moved clarity 4.00 → 3.36 between the PM run and run 1, ~2 hours
  apart, versus 0.04 across this 30-minute pair. **Comparisons separated by
  hours carry more noise than this measurement shows**, and the AM/PM comparison
  reported earlier today spanned twelve.
