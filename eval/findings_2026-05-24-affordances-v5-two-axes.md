# Affordances spike v5 — two-axis rubric (calibration done)

**Spike**: `eval/spikes/affordances_v5_two_axes.py`
**Inputs**:  v4 confidence-calibration failure (all `high` even on wrong labels)
**Outputs**: `affordances_v5_full_output.md` + `affordances_v5_full_summary.json`
**Model**:   `claude-haiku-4-5` (post v0.20 opt-outs)

## What changed since v4

v4 prompt had a single `page_kind_confidence` field that was conflating two
orthogonal things: epistemic uncertainty about the LABEL vs the value of the
extracted CONTENT. The model returned `high` for everything because — from
its perspective — it WAS confident about its classification, even when the
classification turned out to be wrong.

After a brief survey of RAG-eval literature (Braintrust, Deepchecks,
ResearchRubrics paper at arXiv 2511.07685) we adopted the standard split:

```
page_kind_confidence: low | medium | high
  → epistemic uncertainty about the LABEL itself
  → forced low/medium by hard cluster trigger (see below)

content_value: none | low | medium | high
  → how useful the extracted content is to the calling agent
  → OMITTED when page_kind is an obstacle kind (the absence carries the meaning)
```

Two further fixes in the v5 prompt:

1. **Hard cluster trigger** for confidence: if `page_kind` falls in any of
   6 named confusable clusters (academic / landing / dashboard / changelog /
   feed / longform), confidence MUST be ≤ medium — never high.
2. **Envelope discipline** on obstacle pages: when `page_kind` is `error`,
   `paywalled`, `blocked`, or `empty`, OMIT `content_value` + `shapes` +
   `follow_up_questions` entirely. Matches a2web's `_prune_wire` pattern.

## Results — full 30 URLs

| metric                                  | v2 (single axis) | v5 (two axes) |
|-----------------------------------------|-----------------:|--------------:|
| Cost                                    | $0.4863          | $0.5374       |
| Cost / URL                              | $0.0162          | $0.0179       |
| Parse failures                          | 0/30             | 0/30          |
| Fetch failures                          | 0/30             | 0/30          |
| Envelope discipline violations          | n/a              | **0/30**      |
| `confidence` distribution (high/med/low)| 30/0/0           | **25/5/0**    |
| Obstacle detection (error/blocked)      | 4 mislabelled    | **4 correct** |

### Confidence calibration — what moved

5 URLs correctly dropped to `medium` under the hard cluster trigger:

| slug                  | kind         | cluster reasoning                          |
|-----------------------|--------------|--------------------------------------------|
| tiny-arxiv            | reference    | Cluster A (academic): article-short/reference/pdf-stub all plausible |
| tiny-status-page      | product-page | Clusters B+C: status vs product-page (it's a status dashboard) |
| huge-changelog        | changelog    | Cluster D: changelog vs listing            |
| paper-arxiv-pdf-stub  | reference    | Cluster A (same as tiny-arxiv)             |
| docs-cf-page          | product-page | Clusters B+C: landing / dashboard cluster  |

All 5 are honest signals — these ARE genuinely cluster-ambiguous pages.

### Confidence calibration — what stayed `high` (and why)

25 URLs kept `high`. Sampling:

- **Listings** (HN, lobstrs, gh-trending) — Cluster D/E members but the
  structural match is unambiguous (numbered list of stories/items).
- **README** (gh httpx) — Cluster B member but README structural signal
  (header, install, usage, contrib) is dominant.
- **json-feed** (hnrss) — Cluster E but structured JSON is unmistakable.
- **api-reference** (MDN, postgres, anthropic), **spec** (RFC),
  **qa** (Stack Overflow), **source-file** (GH file), **tutorial**
  (fastapi, react.dev), **encyclopedia** (Wikipedia), **video-page**
  (YouTube), **thread** (HN item), **filing** (SEC) — outside clusters
  or with clear singular signal.
- **Obstacles** (4): all `high` because 404/blocked detection is
  unambiguous.

### One real miscalibration

`product-amazon` → `listing` at `confidence=high`. This is wrong (it's a
product page) AND the cluster trigger didn't fire because `listing` and
`product-page` aren't in a shared cluster in the current rubric. **Fix**:
add cluster `G_commerce: {listing, product-page, package-page}` so
Amazon-style hybrid pages trigger the same `medium` deflation.

### `content_value` — the actionable axis

Distribution across 30 URLs:

```
high   ─ 18  rich on-topic extractions (wikipedia, MDN, docs, listings,
                comments, refs, source-file, readme, spa, sec-filing, etc.)
medium ─  5  partial/truncated (changelog, mdn-fetch, amazon, cf, gist)
low    ─  3  thin content correctly flagged
              - tiny-status-page  (758 chars, mostly nav + status grid)
              - docs-anthropic    (726 chars, almost-empty docs stub)
              - media-yt-video    (1013 chars, metadata only)
omitted─  4  obstacle pages (comments-lobste, news-bbc, blog-jvns, gated-nyt)
```

**This is the actionable signal we wanted.** A downstream agent can:
- `content_value: high` → ask follow-ups confidently
- `content_value: medium` → use what's there; consider supplementing
- `content_value: low` → escalate (browser tier? re-fetch?)
- `content_value` missing → page_kind already names the obstacle; don't
  try to ask further

`content_value` does the lifting that `confidence` couldn't. Even when the
model is over-confident on the label, the content_value field tells the
truth about whether anything useful came back.

### Envelope discipline

**Zero violations across 30 URLs.** On all 4 obstacle pages, the model
correctly omitted `content_value` / `shapes` / `follow_up_questions` and
emitted only `{page_kind, page_kind_confidence, reasoning, answer}`. On all
26 content pages, all expected fields were present.

This is rare for prompt-driven envelope discipline — usually you get at
least one off-by-one. The explicit "Content page response: {...}" vs
"Obstacle page response: {...}" template blocks in the prompt seem to have
landed.

## Production design — LOCKED

Three artefacts to ship in the affordances production wiring:

### 1. `AffordancesPayload` boundary type in `packages/llm_extract/`

```python
@dataclass(slots=True)
class AffordancesPayload:
    page_kind: str                      # closed enum below
    page_kind_confidence: str           # "low" | "medium" | "high"
    reasoning: str                      # one-sentence justification
    content_value: str | None = None    # "low" | "medium" | "high"; None on obstacles
    shapes: list[AffordanceShape] = field(default_factory=list)   # empty on obstacles
    follow_up_questions: list[str] = field(default_factory=list)  # empty on obstacles
```

### 2. Page-kind enum (closed set)

```
Content kinds:
  listing | thread | reference | api-reference | tutorial | article-short |
  article-long | changelog | code-snippet | source-file | readme | qa | spec |
  filing | news-article | blog-post | product-page | video-page | json-feed |
  marketing | encyclopedia | package-page | pdf-stub | spa

Obstacle kinds (content_value/shapes/follow_ups omitted):
  paywalled | error | empty | blocked

Catch-all:
  other
```

### 3. Fold into `EXTRACT_CACHEABLE_V1`

Move the affordances block into the existing extraction template's TAIL
(not the cached prefix — must not perturb byte-stable caching). Activate
via `ask(include_affordances: bool = False)`. Default off — keeps the
lean response shape we shipped in v0.14.

Wire-side: `AskResponse.affordances: AffordancesPayload | None` (None
unless opted in).

### Locked decisions, summarised

| decision                                | locked value          |
|-----------------------------------------|-----------------------|
| Default state                           | OFF (`include_affordances=False`) |
| Prompt shape                            | V_CTX_V3 (this spike) |
| Two axes                                | YES (`confidence` + `content_value`) |
| Omit `content_value` on obstacle pages  | YES (envelope discipline) |
| Drop `missed_sections`                  | YES (v1 finding)      |
| Closed shape vocabulary                 | YES (list \| timeline \| key-value \| table \| code \| comments \| citations \| comparison) |
| Hard cluster trigger for confidence     | YES (add `G_commerce` post-spike) |
| Cap follow_up_questions                 | 3-5                   |

## Cost picture for production

Standalone Haiku call on full 30: $0.5374 (~$0.018/URL).

**When folded into the existing `ask` extraction call:**

```
Current ask call:    21k prompt + 200 completion ≈ $0.011/URL
+ affordances:       21k prompt + 700 completion ≈ $0.013/URL  (+$0.002, +18%)
```

The marginal cost (~$0.002/URL) is the only economic shape. v3 spike
proved running affordances as a second call loses almost all the savings
because the dominant cost is prompt tokens (page content), which both
calls pay independently.

## Followups for production wiring

- 🟡 Add cluster `G_commerce: {listing, product-page, package-page}` to
  the cluster trigger before production. (Catches the `product-amazon`
  miscalibration.)
- 🟡 Output-benchmark A/B (`make bench`): run with affordances on vs
  off, confirm answer quality doesn't degrade.
- 🟡 Verify the affordances schema example sits in the TAIL of the
  prompt, not the cached PREFIX. (Cache-prefix integrity check.)
- 🟢 Refresh corpus: `news-bbc`, `comments-lobste`, `blog-julia-evans`
  URLs are stale (404). Replace with fresh URLs before the next eval.
- 🟢 Consider second-order signal: `content_value=low` paired with
  `page_kind` in a content cluster could trigger automatic browser-tier
  escalation. (Telemetry first.)

## Caveats

- 30 URLs is a meaningful sample but not exhaustive. Edge cases
  (interstitial cookie walls, A/B-tested SPAs, IP-blocked pages) not
  represented.
- Costs are list-price reconstruction; OAuth subscriber sees no direct
  billing.
- `product-amazon` and corpus-stale URLs (3 × 404) limit absolute
  classification-accuracy numbers — fix in corpus refresh.
- The model still occasionally claims `confidence=high` on debatable
  cluster picks (`huge-wikipedia → reference` is encyclopedia-vs-reference
  but kept high). The cluster trigger fires only when the model's
  reasoning *names* the cluster — silent over-confidence remains a known
  limit.
