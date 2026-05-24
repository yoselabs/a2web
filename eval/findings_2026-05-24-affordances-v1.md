# Affordances spike v1 — 2026-05-24

**Spike**: `eval/spikes/affordances_v1.py`
**Output**: `eval/spikes/affordances_v1_output.md`
**Model**: `claude-haiku-4-5` via ClaudeCodeProvider (post v0.20 opt-outs)

## Question

When an agent calls `ask(url, question)`, the Haiku extraction sees the entire
page. For ~$0 marginal completion-token cost, could it ALSO emit:

- `follow_up_questions` — 3-5 questions a curious reader would plausibly ask next
- `shapes` — typed data structures present on the page (list, timeline, key-value, code, table, citations, comments, comparison) with location + size
- `missed_sections` — section/heading labels the answer did not touch

…and would those affordances be *useful enough* to surface back to the calling
agent, or would they be vague slop?

## Method

5 diverse URLs (HN front, Wikipedia article, PyPI package, arXiv abstract,
Reddit thread). Production a2web fetch → `content_md` → separate Haiku call with
affordances-augmented prompt → save structured outputs to markdown for hand
review.

## Results

| slug             | fetch tier              | chars  | aff. call  | cost     | usable? |
|------------------|-------------------------|-------:|-----------:|---------:|---------|
| hn-front         | site_handler:hn         |  6 632 | 15.1 s     | $0.0161  | ✅ |
| wikipedia-rust   | site_handler:wikipedia  | 42 295 | 12.4 s     | $0.0183  | ✅ |
| pypi-httpx       | raw                     |  6 711 | 11.7 s     | $0.0173  | ✅ |
| arxiv-abstract   | site_handler:arxiv      |  1 853 | 12.0 s     | $0.0121  | ⚠️ partial |
| reddit-comments  | raw (failed)            |      0 | —          | —        | — |
| **total**        |                         |        |            | **$0.0637** | 4/5 |

## Quality assessment (hand review)

**Follow-up questions** — strong across the board:
- HN: "ranking determined purely by upvotes?", "patterns in which domains appear"
- Wikipedia: "how does the borrow checker prevent memory safety errors?", "2021 moderation team resignation"
- PyPI: "differences between HTTPX and requests?", "why still Beta?"
- arXiv: "how does LoCoMo differ from benchmarks covering up to five sessions?"

These read like questions a competent agent would actually ask next. Not generic
("tell me more"), not slop. **This is the core win.**

**Shapes** — accurate and specific:
- HN correctly labels list + key-value with sizes
- Wikipedia identifies timeline + code blocks + citations distinctly
- PyPI catches release-history timeline + downloads list

The closed-set label vocabulary (list | timeline | key-value | table | code |
comments | citations | comparison) keeps outputs comparable across URLs.
Useful for an agent deciding what to re-extract with a sharper ask.

**`missed_sections`** — weakest field. The arXiv abstract case shows
hallucination risk: the model claims "Abstract", "Introduction", "Methods",
"Results" are missing, but those literally aren't on the page (an arXiv
abstract page IS just the abstract). The other URLs do OK but the field
mixes "real sections that exist on the page but answer didn't touch" with
"sections that *would* be there in a richer version of this page."

**Recommendation**: drop `missed_sections` or reformulate as "page sections
referenced in the markdown but absent from the answer" (verifiable against
the source).

## Cost picture

Spike used a **separate** Haiku call for affordances, ~21k prompt + ~500
completion = ~$0.013/URL. That's ~3x the cost of a bare answer-only call —
expensive for default behaviour.

**Cheap path forward**: fold affordances into the *existing* `ask`
extraction call. The page content + system prompt are already going over
the wire. Marginal cost is only the extra ~500 completion tokens
(~$0.0015/call instead of $0.013/call). ~9× cheaper.

```
Current ask  call: ~21k prompt + ~200 completion ≈ $0.011/call
With affordances:  ~21k prompt + ~700 completion ≈ $0.013/call (+18%)
Separate 2nd call:                               $0.024/call (+118%)
```

**Conclusion**: fold-in is the right shape. Standalone is the wrong shape.

## Design implications

1. **Fold into the existing extraction prompt** (not a separate call).
2. **Opt-in by default** via `include_affordances: bool = False` on `ask`.
   Affordances bloat the response envelope; agents that don't ask for
   them shouldn't pay the completion tokens or carry the noise.
3. **Drop `missed_sections`** — hallucination-prone, and the agent can
   approximate it by comparing returned `headings` against the answer.
4. **Keep `shapes` closed-enum** — comparability across URLs > flexibility.
5. **`follow_up_questions` capped at 3-5** — more is noise, fewer loses
   the "didn't think of that" effect.

## Open questions

- Should `shapes` carry **pointers back to markdown** (e.g.,
  `where: "<heading-slug>"`) so agents can `ask` for that section
  specifically without re-fetching?
- Worth a second pass on a wider corpus (15-20 URLs) before wiring into
  production? The 5-URL spike is suggestive but small.
- The arXiv `missed_sections` slip suggests the model has a strong
  prior about what "should" be on a page of type X. Worth testing
  whether `shapes` has the same prior-driven slop on edge cases.

## Followups

- 🟡 Wire affordances into the `EXTRACT_CACHEABLE_V1` template under an
  `include_affordances` flag (single prompt, additional output fields).
  Add `AffordancesPayload` boundary type to `packages/llm_extract/`.
- 🟡 Surface in `AskResponse` only when `include_affordances=True`.
- 🟢 Run a wider spike (15-20 URLs) before declaring shapes/labels stable.
- 🟢 Investigate Reddit fetch failure (status=failed, 0 chars) —
  separate issue, not affordances-specific.

## Caveats

- 5 URLs is a small sample; quality may degrade on edge cases not surveyed.
- The separate-call cost figures don't reflect the proposed fold-in shape.
- Costs are list-price reconstruction (Claude Code OAuth subscriber sees no
  direct billing).
- One fetch failed (reddit-comments) — not affordances-related.
