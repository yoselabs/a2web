# Finding — `also_here` under-fires on narrow-ask × rich-page (2026-07-11)

## Trigger

Thin post-v2 sanity checks (`wikipedia-rust` bench cell + a live koçtaş probe).
User flagged: a Koçtaş product query returned **no suggested URLs and no
same-page index** — suspicious for an e-commerce page.

```
uv run a2web web query \
  --url=".../einhell-te-cd-18-48-li-i-darbeli-matkap-125-ah-starter-kit/p/5001125801" \
  --query="What is the price of this product, its currency, and is it in stock?"
→ answer: "Price: 4,221.97 TRY ... In stock."   (also_here / other_pages absent)
```

## Instrumented probe (provider=claude-code, guarded — $0 metered)

```
tier:               site_handler? no → raw/json path
structural_form:    product          (classified correctly)
content candidates: trafilatura, json_synth, json_synth, json_synth
digest gate fires:  TRUE             (json_synth present)
links:              55               (non-empty → digest built)
routing.also_here:    []   ← the gap
routing.other_pages:  []
routing.refinement_axes: []
```

## Diagnosis

**Not a cost spike. Not a plumbing bug.** The link digest was built and offered
to the model (55 links, product-classified, json_synth candidates present), so
`also_here` / `other_pages` were fully *possible*. The model emitted nothing.

- **`other_pages: []` is defensible.** The 55 links are category / breadcrumb
  navigation, not question-relevant drilldowns. Koçtaş loads reviews via JS, so
  no reviews link is in the fetched HTML — surfacing one would violate ADR-0014
  (never invent a URL). Empty is honest here.
- **`also_here: []` is the real gap.** A product page carries specs, a
  description, and kit contents that a *price/stock* answer never surfaced. The
  withheld-body index (ADR-0015) should list them. The model is treating
  "answered the asked question" as "covered the page" — the prompt's
  "if your answer already covered the page, emit nothing" clause is winning over
  the "index what you withheld" intent on a narrow ask.

## Regression?

No — the pre-v2 `ask_here` instruction carried the *same* tension ("coverage
inventory of what you left on the table" + "if answer covered the page, emit
nothing"). v2 made the entries terser (query grammar) but did not change this
behavior. It is a pre-existing weakness the narrow-ask case exposes.

## Proposed fix (needs a spike, not a hasty edit)

Strengthen the `also_here` clause in `EXTRACT_ROUTER_V1` to separate
**covered the QUESTION** from **covered the PAGE**: on `structural_form` in
{product, article, reference, thread}, a narrow factual ask almost never covers
the page — index the unsurfaced sections. Keep the listing-orthogonality carve-out
(defer to options/refinement_axes) intact. Validate with a Spike-A-style run on
the cheap provider (the `koctas-product-narrow-ask-index` corpus case now locks it).

## Captured

- `eval/corpus.yaml` → `koctas-product-narrow-ask-index` (standing "never lose a case" rule).
