# Finding — v3: the entity block does not earn its keep (2026-08-03)

`eval/spikes/entity_schema_v3.py`, 10 pages (8 scored) × 3 reps × 3 arms,
`claude-code-sdk` / `claude-haiku-4-5` (subscription, $0 metered).
Raw: `eval/spikes/entity_schema_v3_summary.json`.

v1/v2 asked *"does the schema make a2web say LESS?"* — no. v3 asks the three
questions the user actually needs: **completeness, cost, helpfulness.**

```
  A  control      ships today
  B  free         entity block, model picks the type
  E  recommended  + the page's own declared @type as a RECOMMENDATION
                    ("prefer it unless another type is richer")
```

---

## The headline: it delivers nothing

Coverage = fraction of the page's stated facts that reach a caller who never
sees the page. One fixed inventory per page, arms blinded and shuffled,
structured data explicitly told to count as much as prose.

| payload | coverage |
|---|---|
| **A** answer only (today) | **0.552** |
| B answer only | 0.477 |
| **B `entity_fields` alone** | **0.114** |
| **B answer + fields (what the caller gets)** | **0.517** |
| E answer + fields | 0.519 |

| paired delta | mean | 95% CI | |
|---|---|---|---|
| **B_combined − A_answer** | **−0.036** | [−0.122, +0.050] | null |
| B_fields − A_answer | −0.438 | [−0.596, −0.280] | SIGNIF |
| B_answer − A_answer | −0.076 | [−0.152, +0.001] | null, marginal |
| E_combined − B_combined | +0.002 | [−0.061, +0.065] | null |

**Exchange rate: −0.46 coverage points per 1k extra tokens.** Negative. You pay
~76 completion tokens and the caller receives, if anything, slightly less.

`entity_fields` averages **4.6 fields per page** — despite a prompt clause
saying *"Be EXHAUSTIVE — this is the caller's only structured view of a page
they will never see."* The instruction did not take.

**The answer prose already carries more of the page (55%) than the structured
block does (11%), and the block adds nothing on top of it.**

---

## The recommendation arm changed nothing — for an interesting reason

`E followed the declared type: 0/6`.

On wikipedia-rust the page declares `Article`; E emitted `SoftwareApplication`.
That is the "override if richer" clause **working as designed**, not failing:
the page is an *article about* a programming language, so `Article` describes
the document and `SoftwareApplication` describes the thing.

Which exposes a flaw in the original plan:

> **Most declared schema.org types describe the DOCUMENT, not the SUBJECT.**

Measured directly on what pages publish:

```
  wikipedia   @type=Article   11 fields   name, url, sameAs, author.name,
                                          publisher.logo.url, datePublished ...
  bbc         @type=WebPage    8 fields   description, publisher.name,
                                          publisher.publishingPrinciples ...
```

Those are *publishing* metadata. `Article` / `WebPage` / `WebSite` belong on
a2web's existing `structural_form` axis (what kind of PAGE), not on the entity
axis (what kind of THING). So "if the page declares a type, take it" is right
for commerce (`Product`, `Recipe`, `JobPosting` — genuinely about the subject)
and wrong for editorial pages, where it would push a document type into a field
meant for the subject.

---

## Type stability is still not good enough for a semantic interface

```
  declared pages : 2/4 stable
  inferred pages : 7/12 stable   (58%)
```

Same page, same prompt, different label across reps. v2 measured 62%; v3
measures 58% on the inferred half. **Consistent, and consistently too low** to
support "query the web by type".

---

## The measurement gap that could change the verdict

**The best case for declared entity data was never measured.**

`_declared_types` reads JSON-LD via a separate cheap `raw` fetch. On anti-bot
commerce sites that fetch is blocked even when the orchestrator's real fetch
succeeds:

```
  hepsiburada   declared=(none)     <- but it DOES publish Product JSON-LD
                                       (the ceiling probe saw it on a luckier run)
  allrecipes    declared=(none)     <- Recipe, almost certainly present
  pypi          declared=(none)
```

So the arm meant to test "use the page's own declaration" ran mostly with
nothing to use, and the pages with the **richest** subject-level declarations —
commerce `Product` with price/currency/availability/sku/brand/aggregateRating —
are exactly the ones it could not reach.

**Honest state:**

- **LLM-generated entity block: measured, and it does not earn its keep.**
  4.6 sparse fields, 11% coverage, no combined lift, ~76 tokens.
- **Page-declared entity data: UNDER-measured.** The verdict on it is not in.
  It needs reading from the HTML the orchestrator actually retrieved, not from
  a second fetch that anti-bot blocks.

---

## What this implies

1. **Do not ship the entity block as prompted.** Its measured contribution is
   zero-to-negative and its cost is real. v2's "it does no harm" was true and is
   not sufficient — *"not worse" is not a reason to ship*.
2. **The deterministic path is the one still standing.** a2web already parses
   JSON-LD (`structured_render.py`). Reading entity data from what the page
   published costs **zero tokens**, has **zero wobble**, and is perfectly stable
   — the three problems the LLM path has. It just needs the retrieved HTML.
3. **Split the two axes properly.** Declared `Article`/`WebPage`/`WebSite` →
   `structural_form`. Declared `Product`/`Recipe`/`JobPosting`/`Event` → the
   entity axis. A declared type is not automatically an entity type.
4. **The semantic-interface goal is not blocked by cost — it is blocked by the
   data not existing.** Pages mostly publish document metadata; models produce
   sparse fields. Neither yields the rich, stable, queryable entity the idea
   needs. That is a finding about the web, not about a2web.

## Caveats that could soften this

- Haiku. A stronger model may fill `entity_fields` far more completely; the
  prompt asked for exhaustive and got 4.6 fields, which reads more like model
  capacity than concept failure.
- 8 scored pages, 24 rounds. The combined-coverage CI spans ±0.09.
- Two pages contributed degenerate rows (`hepsiburada` produced
  `entity_type=None` and `entity_fields={}` on every rep of both arms —
  reproducing v2's finding on the same page).
