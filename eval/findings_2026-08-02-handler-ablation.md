# Finding — handler ablation: handlers add INDEX and BODY, not ANSWER (2026-08-02)

`eval/spikes/handler_ablation_v1.py`, 9 sites × 2 reps, handler ON vs
`match_handler` forced to `None`. `claude-code-sdk` / `claude-haiku-4-5`
(subscription, $0 metered per ADR-0016). Raw:
`eval/spikes/handler_ablation_v1_summary.json`.

This is a **screening** result — one URL per handler, two reps. It is enough to
reject "handlers are one category" and enough to rank where to look next. It is
not enough to retire a handler.

---

## The table

| site | ON tier | OFF tier | body ON→OFF | `other_pages` | adjacent ON | adjacent OFF | verdict |
|---|---|---|---|---|---|---|---|
| wikipedia | `site_handler:wikipedia` | `raw` | 41918 → 4650 | 10 → 0 | 0.22 | 0.18 | RENDERING + INDEX |
| github | `site_handler:github` | `raw` | 25557 → 13283 | 10 → 2 | 0.44 | **0.56** | INDEX only |
| habr | `site_handler:habr` | `raw` | 21178 → 11671 | 0 → 0 | 0.30 | **0.72** | **body up, relay DOWN** |
| v2ex | `site_handler:v2ex` | `raw` | 6143 → 4821 | 0 → 0 | **0.65** | 0.55 | mild rendering |
| discourse | `site_handler:discourse` | `browser_robust` | 4583 → **20817** | 10 → 10 | 0.37 | **0.56** | generic beat it |
| hn | `site_handler:hn` | `raw` | 3634 → 3518 | 0 → 0 | 0.70 | **0.89** | redundant here |
| arxiv | `site_handler:arxiv` | `raw` | 2394 → **2686** | 0 → 0 | 0.00 | 0.00 | degenerate |
| reddit | `browser` (superseded) | `browser` | 530 → 530 | 0 → 0 | failed | failed | walled both ways |
| twitter | `browser_robust` (superseded) | `browser_robust` | 670 → 670 | 0 → 0 | failed | failed | walled both ways |

Aggregate, paired within site+rep:

```
  core     recall ON−OFF : +0.050   95% CI [−0.031, +0.131]   n=15   null
  adjacent recall ON−OFF : −0.087   95% CI [−0.179, +0.006]   n=18   null, NEGATIVE
```

---

## Four results, in descending confidence

### 1. NOT ONE handler was retrieval-critical on this corpus

The category the spike most expected to find — "the site is walled and the
handler is the only way in" — **did not occur**. reddit and twitter failed
identically with and without their handlers; both were superseded by browser
escalation before their output mattered.

This is the single most surprising result, and it directly contradicts the
framing in `I0269` §4 (and in the spike's own docstring) that reddit/twitter
handlers exist because those sites are otherwise unreachable. On these two URLs,
today, they are unreachable *anyway*.

Caveat with teeth: both are ALSO the two sites where nothing was retrieved at
all, so this says the handler did not rescue a walled page — not that the
handler never rescues one.

### 2. Handlers reliably add the INDEX

`other_pages`: wikipedia **10 → 0**, github **10 → 2**. This is the clearest
positive effect in the run and it is invisible to the recall metrics, which
score the *answer*, not the index.

That is exactly I0269 §5's claim, and it is the strongest measured argument for
keeping handlers: **the handler's `next_links` are load-bearing where the generic
miner produces almost nothing.** Ablating wikipedia's handler does not degrade
the answer — it deletes the map (ADR-0015's index) entirely.

### 3. Handlers do NOT improve the answer — and trend worse

Core recall is null. Adjacent recall is −0.087 overall, −0.130 across the six
non-degenerate sites, with the generic path winning 4 of 6.

**This survives a bias pointing the other way.** The judge's fact inventory is
built from whichever arm retrieved the larger body — so on the 5 sites where
that was the handler's own body, the generic arm was graded against facts it may
never have received. On exactly those 5 biased-toward-the-handler sites, the
handler still lost 3 of 5, mean −0.118. An effect that survives a bias against
it is more credible than one that needs a favourable one.

### 4. A bigger body is not a better body — habr is the proof

habr's handler produces **1.8× the content** (21178 vs 11671 chars) and **less
than half the relay** (adjacent 0.30 vs 0.72), on an inventory built from the
handler's own larger body. More text, less of the page reaching the caller.

This breaks the assumption running through both I0269 and the spike's own
classifier — that body size proxies handler value. It does not. The classifier
in `_classify` uses `body > 2000` as a RENDERING signal and would have labelled
habr a success; the recall numbers say otherwise. **Treat the per-handler verdict
strings as a first-pass sort, not a judgement** — the underlying columns
disagree with them in at least this one case.

---

## Limits — the ones that would change the conclusions

1. **One URL per handler.** This is the exact weakness `handler_probe.py` was
   rebuilt to fix: *"arXiv's dead parser was on `/list/…` and the probe only ever
   fetched `/abs/…` — the broken shape was not probed at all."* This ablation
   fetched `/abs/`. **The arxiv "degenerate/redundant" reading says nothing about
   the listing shape, which is where that handler's index value lives.** Same
   applies to every multi-shape handler.
2. **n=2 reps.** No CI here excludes a moderate effect.
3. **3 of 9 sites degenerate** (arxiv 0.00/0.00, reddit and twitter failed), so
   the effective sample is six.
4. **Cost and latency unmeasured.** Mitigated by an observation rather than a
   number: **7 of 9 OFF arms landed on `raw`**, the cheapest tier. Only discourse
   escalated (to `browser_robust`). So for most sites the fallback is not an
   expensive browser render — which weakens the "handlers pay for themselves in
   avoided escalation" defence, without disproving it.
5. **discourse's inventory came from the OFF body** (20817 vs 4583), biasing that
   one case toward the generic arm. Discount it.

---

## What this means for the organisation question

It refines, rather than overturns, the part-2 conclusion:

- **Keep the handlers.** The index effect (§2) is real and large, and ADR-0015
  makes the index a product invariant, not a nicety.
- **But their value is `next_links`, not body text.** That inverts the implicit
  model, in which handlers exist to produce a better-shaped body via
  `pre_rendered`. On this evidence the body half is at best neutral and at worst
  negative (habr).
- **This is a direct argument FOR I0269 §5.** If the handler's measured
  contribution is its index, then converging six real `reason` strings onto a
  constant `"item page"` destroys the one thing handlers demonstrably add.
- **The four-way taxonomy holds, but the population is skewed** — no RETRIEVAL,
  two SUPERSEDED, and the rest split between INDEX and body-rendering. That is
  still four different maintenance budgets, which the current flat `handlers/`
  organisation cannot express.

**The measurement worth doing next** is not more reps on these URLs — it is the
same ablation across each handler's *multiple shapes* (listing vs item), because
that is where the index value concentrates and where the one-URL limit currently
blinds this result.
