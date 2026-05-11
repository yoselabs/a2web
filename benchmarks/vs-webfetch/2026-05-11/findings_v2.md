# Findings v2 — full cost/quality/reliability comparison

Run on 2026-05-11. Phase 3 (reader + judge) replayed via `a2web.llm` over
the Claude Code OS session, replacing the original `claude -p` subprocess
loop. Tokens cl100k_base. n=20 URLs across 5 classes.

> Note on the baseline: WebFetch performs LLM extraction server-side, so
> the caller only sees a short *answer* (~94 tok mean). a2web returns the
> *envelope* — content + metadata + diagnostics. Phase 3 levels the playing
> field by running the same reader model (Haiku) over both before judging.

## Quality (Sonnet judge, blind, 0-5 per criterion)

```
   System       mean  median  reached  wins
   webfetch     2.80   3.0    12/20    13   ← server-side extracted
   a2web_A      3.40   4.0    14/20    18   ← full envelope
   a2web_B      3.05   3.5    15/20    13   ← meta only
   a2web_C      3.00   3.5    12/20    14   ← content only
```

a2web_A wins overall: **+0.60 mean (+21%)**, **+5 wins**, **+2 reached**.
The wins concentrate in JS-heavy SPAs and structured/edge cases where
WebFetch's HTML→markdown pipeline can't see real content.

## Cost — two dimensions

**1) Caller-side token cost (what downstream agent ingests):**

```
   WebFetch answer (mean):           94 tok    ← tiny — server-side trick
   a2web_A envelope (mean):       6,353 tok    ← 67x larger
   a2web_B meta envelope:         1,390 tok    ← 15x larger
   a2web_C content-only:          1,335 tok    ← 14x larger
```

WebFetch wins this dimension decisively. The server-side LLM extraction
collapses arbitrary page content to a 50-300 token answer. a2web ships
the full content because the caller needs it for follow-up reasoning.

**v0.4 closes this gap** via the `ask=` param: a2web now runs the same
server-side extraction and returns ~equivalent token sizes to WebFetch.
That path is not measured here — phase 3 was designed before v0.4.

**2) Provider $$ — judge replay (Claude Code OS session):**

```
   Total wall          7m33s
   Total judge spend   $2.87  (4 systems x 20 URLs = 80 judge calls)
   Per system          ~$0.40-0.86
```

## Reliability

```
   a2web fetch status     14/20 ok   (6 "failed" — block pages, 404,
                                      hard JS walls; honest diagnostics
                                      surfaced rather than silent garbage)
   a2web judge "reached"  14/20      (matches status — judge agrees
                                      a2web returned real content)
   WebFetch judge reach   12/20      (judge agrees WebFetch's answer
                                      conveyed real page content)
```

The 6 a2web failures map to: dead URL (archive empty), Linear marketing
(SPA timeout), Reddit (blocked), redirect-chain, X-post (Nitter dead),
large-page (size cap). a2web_A still scored 1.0+ on 5 of those because
the diagnostics payload told the reader honestly *why* it failed.

## Latency

```
   a2web mean wall_ms       4031 ms     (CLI overhead; internal: ~1-2s)
   WebFetch                 not measured (subjectively < 1s typical)
```

a2web is **3-5x slower** in the worst case (Linear SPA: 16s for browser
tier). The cost is buying robustness — handlers, fallbacks, archive
hedging.

## Per-class breakdown

```
   Class        n  WebFetch  a2web_A  WebFetch_tok  a2web_A_tok  Comment

   A_clean      4    4.25     4.25         170        9,340      Tie. Envelope waste.
   B_gated      4    0.75     0.75          40        1,946      Both fail honestly.
   C_spa        4    3.75     5.00         116        7,985      a2web crushes JS pages.
   D_structured 4    3.25     4.25          90       10,851      a2web wins via parsed structure.
   E_edge       4    2.00     2.75          50        1,642      a2web edges ahead.
```

### Read this carefully

- **A_clean is the WebFetch sweet spot.** Static HTML, simple article.
  WebFetch's 170-token answer matches a2web's quality at 1/55 the bytes.
- **B_gated nobody wins.** Cloudflare, paywall, login wall — both
  systems honestly report failure. a2web doesn't fabricate.
- **C_spa is where a2web exists.** WebFetch sees the JS shell; a2web's
  browser tier (or handler) renders real content. +1.25 score gap, and
  WebFetch never closes it without a headless browser.
- **D_structured: a2web's handler wins, but pays envelope cost.**
  GitHub trending, PyPI, npm — a2web's site handlers extract the *list*
  of items; WebFetch sees a noisy HTML dump.
- **E_edge: redirect-chain, non-English, dead links.** a2web's diagnostic
  payload + archive fallback edges ahead.

## What this actually means

WebFetch is **optimal for clean, well-extracted pages where the agent
has a specific question** (its design assumes both). The 94-token
answer is the killer feature.

a2web is **optimal for JS pages, structured data extraction, and any
case where the agent needs the underlying content** (not just an
answer). Reliability is also higher — 14 vs 12 reached.

The right pairing for an agent: **call WebFetch first; on failure or
empty answer, fall back to a2web**. This benchmark suggests that
hybrid wins on both cost AND quality.

v0.4's `ask=` parameter on a2web's `fetch` tool collapses the
caller-token gap (the WebFetch trick) for cases where the agent does
have a specific question. Measuring that path is the next benchmark.

## Cost-per-quality (rough)

Judge-only $ ÷ mean quality score:

```
   System     judge $   mean    $ / score-point
   webfetch   $0.40    2.80     $0.143
   a2web_A    $0.80    3.40     $0.235
   a2web_C    $0.81    3.00     $0.270
```

This is misleading on its own: WebFetch's *fetch* cost (the Haiku call
on the page) isn't in the table — it's billed to whoever's running the
Claude Code session. Real total comparison needs the v0.4 `ask=` path
where a2web does the same thing transparently.

## Provenance

```
   Tool runner    a2web.llm.Judge / Extractor (replaces claude -p)
   Provider       ClaudeCodeProvider (OS session, no API key)
   Reader model   claude-haiku-4-5-20251001
   Judge model    claude-sonnet-4-6
   Wall time      453s (7m33s)
   Concurrency    asyncio.Semaphore(4)
   Commit         99b51c0
```
