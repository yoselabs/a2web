# Bench findings — 2026-08-01 (PM), after the renderer lift

Run: `eval/runs/2026-08-01_132342/` — 42 corpus entries × 3 systems.
Compared against `eval/runs/2026-08-01_011025/` (the AM run, same corpus, same
42 slugs, so system means ARE comparable this time). Provider `claude-code-sdk`
(ADR-0016).

Trigger: `lift-the-item-set-and-renderer` changed listing output and recipe
envelopes, both stated triggers.

## Headline

| System | quality | env tokens | clarity | contract | next_links |
|---|---|---|---|---|---|
| webfetch_baseline | 2.10 | 203 | 4.00 | — | — |
| a2web_detail | 3.40 | 4556 | 1.51 | 42/42 | 3.00 |
| a2web_extract | 3.33 | **771** | **4.00** | 42/42 | 3.00 |

AM → PM, `a2web_extract`: quality 3.52 → 3.33, clarity 3.85 → 4.00, tokens
797 → 771. `a2web_detail`: quality 3.27 → 3.40.

**Do not read the quality moves as a result.** `extract` fell 0.19 and `detail`
rose 0.13 across a change that touched neither answer selection nor extraction.
Both are judge variance over live pages. The bench has no repeat-run baseline,
so it cannot separate a real ±0.2 from noise — that limitation is worth fixing
before anyone tunes against this axis.

## 1. The options byte budget did what it was built for

The three cells that carried the AM regression:

| slug | AM | PM |
|---|---|---|
| `listing-answer-always-leaves-an-index` | 5007 | **3351** |
| `arxiv-listing-partial` | 4730 | **3195** |
| `json-ld-itemlist-leaves-an-index` | 4590 | **4008** |

Verified on the wire that the bound holds rather than trusting the mean: the
`walled-page-with-preceding-info-hint` envelope carries 30 options totalling
**3771 detail characters against the 4000 budget.**

Mean envelope fell 797 → 771 *despite* two cells rising for unrelated reasons
(below), so the underlying drop is larger than the mean shows.

## 2. Two cells rose, and neither is attributable to this change

Checked rather than assumed, because "my change made the envelope bigger" is
the obvious reading and it is wrong here:

- **`walled-page-with-preceding-info-hint` 366 → 2242.** The AM run FAILED
  (`tier=jina`, `status=failed`, `retrieval_incomplete`). The PM run SUCCEEDED
  via the archive tier and returned real content — title, byline, answer,
  `also_here`, `other_pages`. A bigger envelope because the fetch worked. This
  is the better outcome, and reading it as a token regression would have been
  exactly backwards.
- **`medium-tag` 1330 → 2017.** Quality 5 in both runs, no fetch error in
  either; the live page carries more content than it did twelve hours ago.

## 3. Contract conformance held at 42/42 through a package move

The renderer moved to `packages/structured_render.py`, `Recipe` switched from an
allowlist to default-keep, and the table renderer changed its column derivation,
cell cap and row cap. The deterministic envelope check did not move.

## 4. Zero unscored quality cells

126/126 scored, against 125/126 in the AM run and 112/114 on 2026-07-28. The
`bench_judge` degrade seam added this morning (`except AnyLLMError` → a score-0
verdict that SAYS it is an infrastructure failure) is holding: a provider hiccup
no longer kills the run or silently drops the cell.

## 5. `next_links` rose to 3.00 — and is still not readable

Up from 2.56/2.67. **Do not bank this.** The axis re-judges that day's page
content rather than the link set's structure (diagnosed in
`eval/findings_2026-08-01.md` §2, filed to `BACKLOG.md`), so a move in either
direction is dominated by what happened to trend on GitHub overnight. n=9 of 42.

The judge prompt was deliberately NOT changed before this run: altering it
mid-comparison would have made the AM/PM delta unattributable, which is the
same mistake as re-blessing a golden to make a diff go away.
