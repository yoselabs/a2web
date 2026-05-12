# Extraction-quality benchmarks

Measures whether trafilatura + readability (a2web's current extraction
pipeline) miss enough content on real-world pages to justify a Reader-LM
v2 fallback tier.

## The trip decision

The Reader-LM v2 fallback (BACKLOG, v0.2 candidates) trips if **≥10% of
URLs score below 0.7 token-F1** against a hand-curated `gold_md`. Below
that bar, current extraction is good enough; the LLM-based tier is pure
cost. Above it, the fallback earns its keep.

Both thresholds are tunable from the CLI (`--threshold`, `--miss-rate`).

## Workflow

### 1. Build the corpus

Pick 50-100 URLs spanning seven classes (longform_news, blog, docs,
forum, aggregator, spa, js_heavy_news). For each:

```bash
# Fetch the page yourself
curl -L https://example.com/article > raw.html

# Eyeball the rendered version in a browser, then hand-edit a clean
# markdown version as `gold_md` in corpus.yaml.
```

Tip: bias toward content where current extraction is *visibly* lossy in
real a2web cache misses. A clean blog post is uninteresting — pick the
pages that have weird structure, paywall preambles, comment threads,
docs with sidebars.

### 2. Run the eval

```bash
uv run python -m a2web.llm_eval.extraction_cli \
  benchmarks/extraction-quality/2026-05-12/corpus.yaml \
  > benchmarks/extraction-quality/2026-05-12/results.json
```

Output goes to stdout (full per-URL JSON) and stderr (one-line verdict).

### 3. Read the verdict

```
[TRIP] n=87 mean_f1=0.612 below_0.70=14/87 (16.1%); Reader-LM v2
threshold (10%) TRIPPED — recommend fallback
```

If TRIPPED, slice by class — Reader-LM v2 only needs to win the classes
that actually miss. Add the tier only behind verdicts that target those
classes (e.g., `paywall` or `extraction_thin` gate verdicts).

### 4. Iterate gold_md

The harness is honest about both directions. If your gold_md scores low
because *the gold is bad* (you cropped too aggressively, missed a
paragraph), fix the gold. The check is bidirectional: spot any URLs
where token-F1 is low but `length_ratio` is near 1.0 — those are
disagreement-on-content, not extraction-misses-content.

## Scoring primitives

- **token_f1**: bag-of-words F1, lowercased \\w+ tokens. SQuAD-style.
- **length_ratio**: `len(extracted) / len(gold)`. >1.0 over-extracts
  (likely included nav/footer); <1.0 under-extracts (likely dropped
  body paragraphs).

No LLM dependency for scoring — keeps the trip decision deterministic
and cheap.
