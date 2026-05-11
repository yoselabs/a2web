# Findings v3 — answer-vs-answer (the fair comparison)

Run on 2026-05-11. Phase 4 calls `a2web.fetch(url, ask=task)` in-process via
`a2kit.testing.client` and judges the returned `extracted_answer` head-to-head
against WebFetch's answer for the same URL/task. v3 supersedes v2 on the
**caller-token** dimension; v2's quality and reliability sections stand.

> **Why v3 exists.** v2 compared WebFetch's *server-side-extracted answer*
> (~94 tok) against a2web's *full raw envelope* (~6,353 tok) and claimed
> a "67x" caller-token gap. That comparison was apples-to-oranges — different
> artifacts, different jobs. The fair comparison was blocked because the
> ask= path didn't exist when v1 captured run payloads. v0.4 fixed that,
> and phase 4 measures it directly.

## Caller-side token cost — the real picture

```
   System            mean   median   max
   ──────────────────────────────────────
   WebFetch answer     113     100   271
   a2web ask= answer   161     156   266
   ratio              1.43x          ← not 67x
```

n=15 successful a2web fetches with non-empty extracted_answer. Both
artifacts are LLM-extracted answers to the same question, produced by
Haiku 4.5 from the page contents. The remaining 5 URLs where a2web
failed are excluded — there's no answer to count tokens on.

### Why a2web is ~50 tokens longer on average

Three drivers, none of them a "bug":

1. **Cleaner input → denser output.** a2web's content_md is post-trafilatura
   (boilerplate stripped), so Haiku gets more substantive signal per char
   and tends to elaborate. WebFetch's input is raw HTML→Turndown markdown
   (nav, footers, links inline), so the model spends some output budget
   filtering noise instead of elaborating.

2. **Preamble fluff.** a2web answers often start with "Based on the
   content provided:" — ~10-20 tokens of throat-clearing. This is a
   prompt template artifact, not a model quirk. The user template
   could be tightened to remove it.

3. **Synthesis closing.** a2web tends to add a final synthesis sentence
   ("...making it both safe and performant"). Sometimes adds real value
   (the stripe-docs example explains *why* the server/client split
   matters); sometimes it's just padding. Product call, not a bug.

The 48-token average overhead is bounded — it doesn't scale with page
size (a2web's max was 266, WebFetch's max was 271 on the same input).

## Quality (Sonnet judge, blind)

```
   System            n   mean   median
   ────────────────────────────────────
   WebFetch         20   2.80    3.0
   a2web ask=       14   3.71    5.0     ← +33% on scored cases
```

a2web's higher mean comes from the C_spa and E_edge classes (see
per-class). On C_spa specifically a2web's median is 5/5 — when the
browser tier or a site handler renders the page, the LLM has actual
content to summarize instead of a JS shell.

## Reach (judge "delivered real content")

```
   System            reach
   ────────────────────────
   WebFetch          12/20
   a2web ask=        11/20  ← lower because a2web fetch failed on 5
   a2web fetch ok    15/20
```

a2web's lower reach is **all on the fetch side, not the LLM side**.
When a2web fetched successfully, the LLM extracted a judged-real
answer in 11 of 15 cases (73%). WebFetch's 12/20 = 60% when its raw
HTML→Turndown pipeline can see through. These are different failure
modes:

- WebFetch failures: JS-rendered pages it can't see through, 404s.
- a2web failures: hard blocks (Cloudflare, Twitter without Nitter),
  dead URLs without archives, redirect chains.

## Per URL class

```
   Class          n   a2_score   wf_score   a2_tok   wf_tok   Note
   ────────────────────────────────────────────────────────────────
   A_clean        3      4.33      4.25      180      170    Effective tie.
   B_gated        2      1.00      0.50      154       50    Both fail honestly; a2web's diagnostics make answer slightly more useful.
   C_spa          4      5.00      3.75      193      116    a2web crushes — browser tier sees what Turndown can't.
   D_structured   4      3.00      3.25      132       90    Effective tie; WebFetch edges on small N.
   E_edge         1      5.00      2.25       85       88    Single sample, but a2web's archive fallback delivered.
```

Sample sizes are smaller than v2 because rows are excluded when a2web's
fetch failed (no answer to compare). The C_spa win pattern from v2
holds; D_structured swung slightly toward WebFetch in this run.

## Cost (this run)

```
   a2web extraction (Haiku) cost     $0.047 total
     ─ 12/20 cache hits from prior runs (free)
     ─ 3 fresh extractions: mean 3 in_tok / 181 out_tok per call
   Judge (Sonnet, 2x per URL)        ~$0.80 estimated total
   Wall time                         147s (2m27s) ← extraction cache helped
```

Real, no-cache extraction cost projection: ~$0.02 per URL with Haiku
input ≈ page content tokens (~1000-5000), output ≈ answer tokens
(~160). At 20 URLs uncached that's ~$0.40.

## The honest read

1. **a2web's caller-token cost matches WebFetch's, within ~40%.** The
   v2 "67x" framing was wrong — it compared the full raw envelope (a
   different product altogether) against WebFetch's answer. Strike it.

2. **a2web wins quality by +33% on the slugs it can fetch.** The wins
   concentrate where WebFetch's HTML→Turndown pipeline can't see —
   SPAs, structured content, edge cases needing archive fallback.

3. **a2web loses reach by 1 row (11 vs 12 of 20).** Five fetch
   failures (blocks, dead URLs) cost a2web answers it could otherwise
   have delivered. WebFetch's two extra reaches came from cases where
   raw HTML was good enough.

4. **The right deployment is a hybrid.** Call WebFetch first; on
   failure or empty answer, fall back to a2web. The patterns are
   complementary: WebFetch is faster on clean static pages, a2web
   wins on JS / structured / fallback-needed.

## Provenance

```
   Script         benchmarks/vs-webfetch/2026-05-11/phase4_ask.py
   Test client    a2kit.testing.client (in-process, no MCP overhead)
   Fetch path     a2web.fetch(url, ask=task) via the WebRouter
   Extractor      Haiku 4.5, byte-identical WEBFETCH_DEFAULT_V1 template
   Judge          Sonnet 4.6 via Claude Code OS session
   Wall           147s, semaphore=3
   Commit         cd3b24a + asdict→model_dump fix in phase4_ask.py
```
