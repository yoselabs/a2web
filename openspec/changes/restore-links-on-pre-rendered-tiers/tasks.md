# Tasks

## 1. Prove the failures before fixing them

- [x] 1.1 Failing test: a link-dense HTML fixture through the browser tier's
      installation path yields a non-empty `fc.links` whose count is commensurate
      with the fixture's anchors. MUST fail today. Use a known anchor count as
      the non-vacuity floor — "not empty" passes on one stray boilerplate link.
- [x] 1.2 Failing test: `content_md` from the same fixture preserves link targets
      (`](` present, count commensurate). MUST fail today.
- [x] 1.3 Failing architecture test: no direct `trafilatura` import or call
      outside the permitted funnel. MUST fail today, naming all six current
      offenders. Carry a `_walk.walked_files(minimum=…)` floor.
- [x] 1.4 Record each failure's output in the commit message. Three guards, three
      witnessed failures.

## 2. Route the bypasses through the shelf extractor (D1)

- [x] 2.1 `tiers/browser.py` — delete `_to_markdown`, call
      `content_extract.extract_markdown(html, url, include_links=True)`.
- [x] 2.2 `tiers/archive.py` — same.
- [x] 2.3 `handlers/wikipedia.py` converted. `reddit`/`twitter` EXEMPT (shelf has no
      `include_comments`; comment threads need it) — recorded as a shelf gap.
      ORIGINAL:
      same. NOTE these also call `trafilatura.extract_metadata`; the shelf
      exposes `parse_metadata`, already imported by `fetcher.py`.
- [x] 2.4 Remove every now-unused `import trafilatura` from `src/a2web/`.
- [x] 2.5 Confirm 1.3 passes.

## 3. Carry links across the pre-rendered seam (D2)

- [x] 3.1 `Rendered` gains `links`, typed like `headings` already is.
- [x] 3.2 Each HTML-serving producer fills it from the `ExtractedContent` it now
      holds. NO second parse — if a producer would need one, it belongs in the
      deferred not-HTML group instead.
- [x] 3.3 `_phase_extract`'s pre-rendered branch sets `fc.links` from the payload,
      alongside the four fields it already copies.
- [x] 3.4 Confirm 1.1 and 1.2 pass.

## 4. Gate

- [x] 4.1 `make check` green, coverage ≥85%.
- [x] 4.2 `make arch` green; `uv run tach check` clean.
- [x] 4.3 Every new guard watched failing (task 1) and carrying a non-vacuity
      assertion.

## 5. Measure the markdown trade-off before keeping it (D2 risk)

- [x] 5.1 Render 3-5 real fixtures with and without `include_links=True`. The
      offline check showed list bullets collapsing and items running together;
      establish whether that holds on real pages.
- [x] 5.2 If content quality degrades materially, keep the funnel + `Rendered`
      links (which need no flag) and drop the inline-link half. The two are
      independent by construction — say which shipped and why.

## 6. Evidence — the live run

- [ ] 6.1 Re-run the subset that found this: `--only listing --axis next_links
      --mode detail` on a subscription provider (ADR-0016). Confirm
      `listing-answer-always-leaves-an-index` and `reddit-listing` now emit a
      candidate block, i.e. their disposition moves from `unscored` to `scored`.
- [ ] 6.2 Full-corpus `make bench` for the token-cost delta. `content_md` with
      inline links is larger and a populated digest adds prompt tokens on pages
      that previously sent none; the envelope-diet work fought for those tokens.
- [ ] 6.3 Write `eval/findings_<date>.md`. State plainly that `other_pages`
      quality on browser-served pages is a FIRST observation — the axis has one
      prior data point ever (mean 3.17, 2026-07-28) and none on this population.
      Poor first numbers are a baseline, not a regression.
- [ ] 6.4 Record, do not fix, whatever the newly-reachable index surfaces.

## 7. Close the loop on the root cause

- [x] 7.1 BACKLOG: record that the bypass predated no shelf gap — the canonical
      extractor was imported by `fetcher.py` the same day `tiers/browser.py` went
      around it, and each promotion (`extract/` → `packages/` → shelf) moved the
      canonical copy further away while the bypass stayed.
- [x] 7.2 BACKLOG: name the remaining unfunnelled libraries with canonical
      wrappers (`httpx` ×4, `aiosqlite` ×3, `yaml` ×2) as candidates for the same
      guard. Do NOT add those guards here — check first whether each actually has
      a canonical wrapper being bypassed, or is legitimately direct. A guard
      written from a pattern still has to earn its floor.
- [x] 7.3 CLAUDE.md: add the trafilatura funnel to the enforced-invariants list,
      beside the `json.loads` funnel it mirrors.
