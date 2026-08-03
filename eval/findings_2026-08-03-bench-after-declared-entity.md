# Bench after the ADR-0018 pass — what moved, and what I cannot attribute

Run `eval/runs/2026-08-03_161513`, 47 URLs x 3 systems, 141 rows, 860s.
Provider `claude-code-sdk` on every row (subscription; ADR-0016 intact — the
`$10.57` in `cost.md` is the notional metered-equivalent the report computes,
not billing).

Ran because three shipped changes touch output quality or cost: the
`declared_entity` wire field, the `_ENTITY_TYPES` deletion, and the
`_wire_content_md` concatenation fix.

---

## The three new corpus cases pass live

This is the part the run establishes cleanly.

```
  slug                                    system    qual clar contract tokens
  recipe-declares-what-the-answer-omits   extract     5    5    PASS     610
  declared-entity-cap-...-truncation      extract     5    5    PASS     927
  chrome-must-not-displace-...            extract     4    5    PASS     474
                                          baseline  3/5/4  4/4/4  —    52/285/300
```

`contract_pass_by_system` is **47/47 for both a2web systems**. That means
`declared_entity_type`, `declared_fields_min` and `declared_omitted_min` all
fired against live pages — including the cap firing on Coursera and declaring
its own remainder, which is the assertion the whole `DECLARED_FIELDS_CAP`
decision rests on.

`chrome-must-not-displace-the-content-payload` passing is the live witness for
the selection bug: SparkFun declares four entities, three of them chrome, and
the subject won.

---

## The comparable-set means went DOWN, and I cannot attribute it

Against `eval/findings_2026-08-02.md`, the last recorded bench:

| | 2026-08-02 | 2026-08-03 | raw delta |
|---|---|---|---|
| webfetch_baseline | 1.95 (41) | 2.19 (47) | +0.24 |
| a2web_detail | 2.95 (43) | 2.72 (47) | **−0.23** |
| a2web_extract | **2.98** (44) | 2.89 (47) | **−0.09** |
| clarity detail | 1.46 | 1.38 | −0.08 |
| clarity extract | 4.35 | **3.86** | **−0.49** |
| tokens detail | 4,494 | 3,429 | −1,065 |
| tokens extract | 749 | 742 | −7 |
| next_links extract | 3.78 | 4.22 | +0.44 |

**The corpus grew by my own three cases, and that makes the drop worse, not
better.** Those cases scored 5/5/4 for `extract` — well above the 2.89 mean —
so they pulled the average UP. Backing them out of the comparable 44:

```
  a2web_extract   (2.89 x 47 - 14) / 44 = 2.77   vs 2.98   -> -0.21
  a2web_detail    (2.72 x 47 -  6) / 44 = 2.77   vs 2.95   -> -0.18
```

So on the like-for-like set both a2web systems are down ~0.2, and `extract`
clarity is down ~0.5.

**I am not going to call that a regression, and I am not going to call it
noise.** What is actually known:

1. **The corpus is not frozen between runs** and the network is not stable.
   46 of 141 rows recorded a fetch error this run — reddit hit
   `block_page_detected` on three cases, `koctas` and `g2` returned `paywall`,
   twitter timed out at the browser. Those are machine-and-day facts (this
   host has **no proxies, no paid-tier keys, jina unreachable**), and they
   differ run to run.
2. **`BACKLOG.md` already says this bench cannot separate a real quality move
   from noise** (2026-08-01, "the bench cannot separate a real quality move
   from noise", S, eval correctness). That entry is open. A ~0.2 shift is
   exactly the magnitude it was filed about.
3. **`declared_entity` is very unlikely to be the cause of the clarity drop.**
   `declaration_rate_v6` measured 7–17% of corpus pages declaring anything
   subject-level. On 47 URLs that is roughly 3–8 pages. A field appearing on
   ≤8 of 37 scored clarity cells cannot move that mean by 0.49.
4. **The token drop IS plausibly mine.** `a2web_detail` fell 4,494 → 3,429
   (−24%), and `detail` is `fetch_raw`, whose body is exactly what the
   `structured_render` changes touch: the empty-header suppression removes
   stubs and `_ENTITY_COUNT_CAP = 12` bounds entity floods. That is the
   expected direction and roughly the expected size.

**The axis warning matters too.** The run exited 5 (`THIN AXES`):
`next_links` scored 9 of 11 requested cells for both a2web systems, below the
90% coverage floor. The harness's own words: *"the numbers are real but the
SAMPLE narrowed"* — so the `next_links` row in the table above is not
cross-system comparable and should not be read as a +0.44 win.

---

## What this run does and does not license

**Does:**

- The `declared_entity` field works end to end on live pages, and its cap
  declares its own truncation.
- The chrome-displacement bug is fixed and has a live witness.
- `a2web_extract` still delivers more than the WebFetch baseline (2.89 vs 2.19)
  at ~3.4x the tokens, and `a2web_detail`'s body got materially cheaper.

**Does not:**

- It does not establish that this session's changes were quality-neutral. The
  comparable-set means moved down ~0.2 and the instrument cannot resolve that.
- It does not establish that they were harmful either.

**The honest next step is not another bench run** — a second sample from an
instrument that cannot resolve the effect gives a second unresolvable number.
It is the open `BACKLOG` item: make the bench able to separate a move from
noise (paired deltas within a case, replicates, an interval), which is exactly
the machinery the `entity_schema_v*` spikes had and the bench does not. Until
then, the deterministic `contract` axis is the part of this run worth trusting,
and it is 47/47.
