# Finding: in-body link grounding — inline v2 rejected; context-snippets is the fallback (2026-07-11)

**Question (task 7.1 / design D1 + Open Q#1):** the v1 digest feeds links as
out-of-band `{{n}}` handle lines (`{{1}} customer reviews · /p/…-yorumlari`),
losing POSITIONAL GROUNDING (the link in its prose context). Should we enable
`include_links=True` and post-process trafilatura's inline `[label](url)` →
`[label]({{n}})` so grounding is regained with a unified closed handle set?

## History of this decision (both false starts recorded)

1. First probe **mis-configured** — stacked `include_links` on top of the FULL
   digest (double-count) and measured raw `content_md` growth (+32%/+113%).
   Wrongly read as "reject on cost." The +113% was Wikipedia, an ARTICLE that
   gets no digest anyway.
2. Corrected to the D1 union (inline in-body + selectolax **set-difference** for
   chrome) — ≈ token-neutral for product/listing. Reopened as viable.

## Fable-council review (fresh Fable 5, 2026-07-11) — the decisive input

The inline-placeholder path (D1 union / Open Q#1 (b)) is **rejected**, for
reasons cost-analysis missed:

- **Answer leak (initially called the killer — now NEUTRALIZED, see below).** An
  inline `[reviews]({{1}})` the extractor reads can be echoed into `answer` →
  `{{1}}` reaches the caller. **Update:** rehydrating the answer text with the
  same `rehydrate_text()` (SHIPPED defensively in v1) turns that handle into a
  real URL, not garbage — so this is no longer a blocker, and is in fact a
  potential FEATURE (see `findings_2026-07-11-answer-inline-links.md`). What still
  argues against the *inline-in-content_md* path is only the milder items below
  (wire divergence, table restructuring) + the fact grounding is unproven — not a
  leak. The **answer-inline-links** hypothesis (links in the answer via the
  out-of-band digest, no include_links) is the live descendant of this idea.
- **`include_links` side effects (VERIFIED, milder than Fable claimed).** LLM-free
  probe (extract both ways, strip link markup from the `on` output, compare text):
  on a product-like page (PyPI) the text is **near-identical — 0.98 similarity,
  differences are whitespace only** — so `include_links` is essentially additive
  there, NOT a content-selection change. Fable's "changes WHAT is extracted" was
  overstated for the target genre. The real effect shows only on complex pages:
  Wikipedia diverges ~16% because **tables/dense-link regions re-render** (a link
  inside a table cell reshapes the table) — but that's an article, not a product
  page. Residual real cost: `content_md` rides the `fetch_raw` +
  `ask(include_content=True)` wires, so inline markers would still need a divergent
  extractor-seam-only copy. NOTE: this is the SECONDARY reason; the answer-leak
  above is decisive on its own and independent of extraction cleanliness.
- **If ever built:** exact-string-substitute `](href)` against the KNOWN
  selectolax href set (not generic markdown parsing); real risk is
  URL-canonicalization mismatch between the two extractors' URLs.

Two risks Fable raised do NOT bite v1 (arguments FOR out-of-band): extractor
cache is skipped on routing requests (no stale cached handles); `{{n}}` collides
with SSR `{{...}}` only INLINE, never in the out-of-band integer-handle field.

## Verdict

- **v1 (out-of-band closed-set `{{n}}` handles) is the right design — keep it.**
- **Do NOT build inline placeholdering / `include_links` for grounding.**
- **If eval shows flat labels genuinely failing**, add **digest context snippets**
  first — ~80 chars of the selectolax parent-node text per digest line, gated to
  vague labels. Out-of-band, no answer-leak, no `include_links`, ~30 lines. ~80%
  of the grounding at ~10% of the surface area.
- This is a HYPOTHESIS until the `affordance` corpus cases prove the flat digest
  fails — an LLM bench, run when not token-constrained.

`content-extract-v0.2.0` `include_links` capability stays available for other
consumers; a2web does not exercise it. Label-less contact retention (the other
half of that EVOLVE) stays live.
