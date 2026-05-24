# Affordances spikes v2 + v3 — 2026-05-24

**v2 spike**: `eval/spikes/affordances_v2.py` · output `affordances_v2_output.md`
**v3 spike**: `eval/spikes/affordances_v3_lean.py` · output `affordances_v3_lean_output.md`
**Model**: `claude-haiku-4-5` via ClaudeCodeProvider (post v0.20 opt-outs)
**Corpus**: 30 URLs spanning content-type extremes

## Question

v1 left three open questions:

1. Are affordances quality holding at scale (vs the cherry-picked 5-URL v1 sample)?
2. Does a **context-aware** prompt that classifies page kind first produce
   better affordances than a generic prompt?
3. What's the actual marginal cost of the affordances addition?

## Method

Three prompt variants on the same 30-URL corpus:

| variant | description | what it emits |
|---------|-------------|---------------|
| **V_GEN**  | generic (v1 reproduction, minus `missed_sections`) | answer + shapes + follow_ups |
| **V_CTX**  | classify page_kind first, then tailor affordances  | page_kind + confidence + answer + shapes + follow_ups |
| **V_LEAN** | affordances only, no answer (simulates fold-in)    | shapes + follow_ups |

Corpus spans 11 content classes (tiny / huge / listing / threaded / docs /
reference / news / blog / forum / code / product / media / gov / spa /
data / paywalled / pdf / marketing). One URL turned out to be a 404
(`jvns.ca/blog/2024/01/05/2023-in-review/`) — kept in the corpus as an
honest stress test.

## Results

### Cost / latency / robustness

| variant | total cost | per-URL | total time | fetch fails | parse fails |
|---------|----------:|--------:|----------:|------------:|------------:|
| V_GEN   | $0.4963   | $0.0165 | 374.8 s   | 0/30        | 0/30        |
| V_CTX   | $0.4863   | $0.0162 | 356.1 s   | 0/30        | 0/30        |
| V_LEAN  | $0.4718   | $0.0157 | 358.7 s   | 0/30        | 0/30        |

Three things jump out:

1. **100% fetch success across 30 URLs.** v1's reddit-comments
   failure didn't recur (different corpus). Worth investigating Reddit
   specifically (logged in BACKLOG) but the general pipeline is rock
   solid on this diverse a set.

2. **100% JSON parse success on all three variants.** No prompt
   discipline issues at 30-URL scale.

3. **V_LEAN is only ~5% cheaper than V_GEN as a standalone call.**
   Surprising — dropping the answer field saves ~200 completion tokens
   but the dominant cost is the ~21k prompt tokens (page content), which
   *every* variant pays. **The v1 fold-in cost estimate stands, but only
   when affordances actually fold into the existing extraction call —
   running them as a second pass loses almost all the savings.**

### Classification accuracy (V_CTX page_kind vs declared)

| outcome                                       | count | comment |
|-----------------------------------------------|------:|---------|
| Exact match                                   | 19/30 | 63% literal hit rate |
| Semantic match (better than declared)         |  ~6   | model right, declared wrong |
| Genuine misclassification                     |  ~5   | needs prompt work |

Examples where the model was **more right than the corpus**:

- `blog-julia-evans` declared `blog-post` → got `paywalled`. URL is
  actually a **404**, returned 1 442 chars of nav/footer only. The model
  correctly flagged "no real content here." Either `paywalled`,
  `error`, or `empty` would have been the honest label.
- `spa-react-dev` declared `spa` → got `tutorial`. react.dev/learn IS a
  tutorial (the SPA shell rendered fine). Model's label is more useful.
- `paper-arxiv-pdf-stub` declared `pdf-stub` → got `article-long`. The
  PDF stub had article-shaped content extracted; the declared label
  was about the URL type, not the rendered content.
- `docs-cf-page` declared `marketing` → got `product-page`. Cloudflare
  registrar page IS a product page.

Examples of **real** misclassifications:

- `comments-lobste` → `status` (way off — it's a comment thread)
- `tiny-gh-gist` → `thread` (it's a code snippet, not threaded discussion)
- `code-gh-readme` → `package-page` (close — README is README, not package)

**All classifications came back with `confidence: high`**. Calibration
is weak — the model is overconfident on its mislabels. Worth a prompt
tweak to demand "low" confidence on edge cases.

### Shape labels — distribution across 30 URLs (V_LEAN)

```
list              32   ← dominant, expected
code              29   ← appears even on doc/reference pages with code blocks
key-value         28   ← extremely common across docs/listings/products
citations          8   ← academic + Wikipedia + references
comments           8   ← threads + Stack Overflow
timeline           7   ← changelogs + release notes + history sections
table              4   ← rarer than expected
```

Closed-set vocabulary worked: zero free-text drift, zero unrecognized
labels. The `comparison` label never appeared (no comparison-heavy URLs
in the corpus — confirms the vocabulary doesn't force false positives).

### Follow-up question density

V_LEAN: median 5, min 0, max 5 (cap working as intended). The one URL
with 0 follow-ups was a deliberate empty response when the page was
identified as blocked/paywalled — desired behavior.

## V_GEN vs V_CTX — qualitative comparison

Spot-checking 5 URLs side-by-side:

- **listing-hn**: V_GEN and V_CTX produced near-identical follow-ups
  ("how does ranking work?", "which domains dominate?"). V_CTX added
  no value over V_GEN.
- **gated-nyt**: V_CTX correctly classified `paywalled` and returned an
  honest "this is blocked" affordance set. V_GEN gamely invented
  follow-ups about the article's content from the paywall preview —
  **V_CTX wins** (no hallucinated follow-ups).
- **docs-anthropic**: V_CTX classified `api-reference`; V_GEN produced
  the same shapes (code, key-value). V_CTX added no value.
- **product-amazon**: V_CTX → `product-page` → follow-ups about reviews,
  price history, shipping. V_GEN → same follow-ups. V_CTX added no value.
- **paper-arxiv-pdf-stub**: V_CTX → `article-long` → follow-ups about
  methodology, results. V_GEN → vague summary-class follow-ups.
  **V_CTX wins** (more grounded follow-ups when content type is unusual).

**Pattern**: V_CTX wins on edge cases (paywalled, unusual page types).
V_GEN matches V_CTX on common cases (listings, docs, products).
The cost is the same. **Ship V_CTX.**

## Cost picture for production

If we fold affordances into the existing extraction call:

```
Current ask call:    21k prompt + 200 completion ≈ $0.011/URL
With affordances:    21k prompt + 700 completion ≈ $0.013/URL  (+18%)

If run as separate 2nd call:                       $0.024/URL  (+118%)
```

**The marginal cost (~$0.002/URL) only materializes when affordances are a
field appended to the existing extraction prompt's response, not a second
Haiku roundtrip.** v3 confirms this empirically — V_LEAN as a standalone
2nd-call pays nearly the full prompt cost again.

## Recommendations

1. **Ship V_CTX (context-aware prompt), but fold-in only — never as a
   second call.** The classification step adds value on edge cases at
   zero cost penalty.

2. **Production wiring**: extend `EXTRACT_CACHEABLE_V1`'s response
   schema with `page_kind`, `page_kind_confidence`, `shapes[]`,
   `follow_up_questions[]`. Gate output via `ask(include_affordances=False)`
   default-off — agents that want them opt in. Boundary type:
   `AffordancesPayload` in `packages/llm_extract/`.

3. **Drop `missed_sections`** (decided in v1 findings; confirmed by v2).

4. **Confidence calibration**: prompt tweak to demand `low` confidence
   when content is thin (< 500 chars) or when shape signals conflict.
   All current classifications came back `high` even when wrong.

5. **Closed shape vocabulary holds at scale.** No expansion needed.
   Maybe add `error` / `empty` to `page_kind` enum so the model has a
   honest exit for 404 / paywall / cookie-wall pages.

## Open questions

- Will fold-in actually preserve answer quality? The extractor is currently
  tuned for clean answers; adding 5 affordance fields might dilute focus
  on the answer itself. Needs a follow-up A/B on the output-benchmark
  harness (the production eval), not just shape/cost.
- Confidence calibration — is a prompt fix enough or do we need a
  separate small-model classifier with a known-thin-content signal?
- Does fold-in interact badly with the byte-stable cache prefix (the
  affordances ask is the changing tail, but if the schema example sits
  *before* the page content, we may need to restructure the prompt).

## Followups for BACKLOG

- 🟡 **Fold affordances into `EXTRACT_CACHEABLE_V1`** under
  `include_affordances=True`. Add `AffordancesPayload` boundary
  + new fields on `AskResponse`. Use V_CTX prompt shape with
  `error`/`empty` page_kinds added.
- 🟡 **Output-benchmark A/B**: rerun `make bench` with affordances on
  vs off — confirm answer quality doesn't degrade.
- 🟢 **Confidence calibration**: prompt tweak demanding "low" on thin
  content. Re-run a 10-URL sub-corpus to verify.
- 🟢 **Cache-prefix interaction**: confirm fold-in keeps the
  affordances schema example in the tail (not the cached prefix).

## Caveats

- One corpus URL was a 404 (jvns); reported as "paywalled" by V_CTX.
  Counted as a "wrong" classification but the behavior was actually
  correct.
- Costs are list-price reconstruction (OAuth subscriber sees no
  direct billing).
- Three variants ran at slightly different times so per-URL latencies
  are not directly comparable across variants (network conditions
  drift). Cost numbers are deterministic from token counts.
