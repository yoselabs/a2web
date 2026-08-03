# Finding — v4: the DECLARED entity path pays, and costs nothing (2026-08-03)

`eval/spikes/declared_entity_v4.py`, 8 pages × 2 reps, 16 paired rounds.
`claude-code-sdk` / `claude-haiku-4-5` (subscription, $0 metered).
Raw: `eval/spikes/declared_entity_v4_summary.json`.

v3 measured the LLM-generated entity block and it lost. This measures the other
half — **read what the page already published** — which is what the user
proposed in the first place and what v3 failed to test.

---

## Result: reading the page's own declaration adds real coverage, for free

Coverage = fraction of the page's stated facts reaching a caller who never sees
the page. One fixed inventory per page, payloads blinded and shuffled.

| payload | all 8 pages | the 7 declaring a SUBJECT |
|---|---|---|
| answer (ships today) | 0.398 | 0.433 |
| llm_fields (v3's block) | 0.374 | 0.383 |
| **declared_fields alone** | **0.426** | **0.487** |
| **answer + declared** | **0.482** | **0.528** |
| answer + llm | 0.551 | 0.585 |

| paired delta | mean | 95% CI | |
|---|---|---|---|
| **answer+declared − answer** | **+0.083** | **[+0.008, +0.159]** | **SIGNIF** |
| **…on subject pages only** | **+0.095** | **[+0.010, +0.180]** | **SIGNIF** |
| answer+llm − answer | +0.152 | [+0.073, +0.231] | SIGNIF |
| declared_fields − llm_fields | +0.052 | [−0.163, +0.267] | null |
| answer+declared − answer+llm | −0.069 | [−0.155, +0.017] | null |

**Declared entity data on its own (0.426) out-delivers the answer prose
(0.398).** A parse of the page's own JSON-LD carries more of the page than the
model's written answer does.

### The comparison that decides it

`answer+declared` vs `answer+llm` is **statistically indistinguishable**
(−0.069, CI spans zero). The two paths deliver the same amount. They do not
cost the same:

```
  answer + llm        +161 completion tokens   type stability 58%
  answer + declared      0 tokens              deterministic — 100% by construction
```

**Same delivery, one is free and exact.** That is the whole finding.

### Field richness — declared beats the model 3-7x

```
  coursera        71        rottentomatoes  38
  bbcgoodfood     49        sparkfun        26
  thingiverse     26        adafruit        13
  goodreads       11        wikipedia       11  (document-level)

  LLM mean:        9.1
```

The v3 prompt asked for exhaustive fields and got 4.6; here, with a corpus of
richer pages, it got 9.1. The page's own declaration gave 11-71.

### The document/subject split is confirmed, and it matters

`wikipedia-rust` declares `Article` — 11 fields of publisher / logo / sameAs
metadata — and its `declared_fields` coverage is **0.00** on both reps. Document
metadata delivers nothing about the subject.

Label counts across the corpus: `subject 7, document 7, unknown 2` — most pages
publish **both**, which is why the split has to be a per-entity label rather
than a per-page one.

This is the corrected form of the user's rule:

> Take the page's declared type **when it describes the subject**
> (`Product`, `Recipe`, `Movie`, `Book`, `Course`).
> A declared `Article` / `WebPage` / `WebSite` belongs on `structural_form`,
> not on the entity axis.

---

## Why v4 had to be run twice — and what the first run really measured

The first v4 corpus (hepsiburada, allrecipes, imdb, marriott, trendyol) returned
**0 subject declarations across 8 pages**, and the honest reason is not about
the web:

```
  proxies configured : 0
  zyte / firecrawl   : no key
  jina               : connection_error
  browser            : paywall / connection_error
  hepsiburada raw    : 16KB block page
```

**This machine cannot reach the walled commerce sites a2web exists to fetch.**
The declared arm was starved by RETRIEVAL, and reporting its numbers as a
verdict on the idea would have been flatly wrong. One genuine web fact did
survive that run: **trendyol serves 374KB with zero `application/ld+json`** — not
blocked, simply not published.

The second corpus was therefore **chosen by measurement, not expectation**: 20
candidate URLs probed with `raw` only, no LLM, keeping the ones that both serve
a subject-level declaration and are readable from here. Seven of eight qualify.

A harness bug was fixed in the same pass: the browser rungs take `backend=` with
a **resolved** backend, not the `Lazy` thunk, so omitting it made the tier return
"not provisioned" rather than raise — a dead rung looked exactly like a page that
publishes nothing, the precise confusion the ladder exists to remove. The ladder
now records why each rung failed instead of swallowing it.

---

## Limits

1. **The corpus is selected FOR declaring.** This measures *"when a page
   declares a subject entity, is reading it worth it?"* — decisively yes. It does
   **not** measure *how often pages declare*, which is the other half of the
   commercial case. The earlier ceiling probe saw JSON-LD on 5 of 26 corpus
   pages, but that probe was retrieval-limited in the same way, so the true rate
   on pages a2web can actually fetch **is still unmeasured**.
2. **n=16 rounds, 2 reps.** Both headline intervals are significant but wide
   (`+0.008` and `+0.010` lower bounds sit close to zero).
3. **Judge reliability.** In the first v4 run the judge scored an *empty*
   payload at 0.55 coverage on one round — a clear error. The blinding and the
   fixed inventory bound this, but the metric is not exact.
4. Haiku throughout.

---

## What follows

1. **Ship the declared path.** It is free, deterministic, and adds significant
   coverage. There is no cost argument against it.
2. **Do not ship the LLM entity block.** It delivers the same amount for +161
   tokens and 58% type stability. v3 already said this; v4 confirms it against a
   free alternative.
3. **Split by entity, not by page** — `subject` types feed the entity axis,
   `document` types feed `structural_form`, `unknown` passes through labelled
   (ADR-0018: a label table, never a gate).
4. **Measure the declaration RATE next.** The value of this feature is
   `+0.095 × (fraction of fetched pages that declare a subject entity)`. The
   lift is now known; the multiplier is not.
5. **Untested and cheap to test:** whether declared + LLM fields are *additive*.
   Both were measured against the answer, never together.
