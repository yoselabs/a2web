# Finding — v5: the declared payload saturates at ~20 fields (2026-08-03)

`eval/spikes/declared_cap_v5.py`, 8 pages × 2 reps × 5 caps, 16 paired rounds.
`claude-code-sdk` / `claude-haiku-4-5` (subscription, $0 metered).
Raw: `eval/spikes/declared_cap_v5_summary.json`.

---

## Correcting v4 before anything else

v4 concluded the declared path "costs **zero tokens**". That is true of
**generation** and silent on **transmission**, which is where the cost actually
lands: the fields go on the wire and the caller — itself an agent, paying
context — reads every one.

```
  coursera        71 fields  ~1993 tokens
  bbcgoodfood     49         ~1127
  rottentomatoes  38          ~803
  goodreads       11          ~120

  mean ~704 · median ~501     the answer they accompany: ~155
```

So the uncapped declared payload is **~4x the answer**. Measured against the
LLM block v4 rejected (~280 tokens for +0.152), the uncapped declared path is
*less* token-efficient, not more. v4's verdict was right about the mechanism
(free, exact, deterministic, no wobble) and wrong to present it as costless.

This spike asks the question that correction forces: **does coverage saturate,
so a cap buys the benefit without the bill?**

---

## Result: yes, at about 20 fields

Coverage = fraction of the page's stated facts reaching a caller who never sees
the page. One fixed inventory per page; payloads blinded and shuffled. Every
arm is `answer + declared_fields[:cap]`, so the only variable is the cap.

```
     cap  coverage     lift     +/-  wire~tok  median   lift/1k
       5     0.506   +0.087  0.106       122     112     0.715
      10     0.530   +0.111* 0.105       243     210     0.457
      20     0.618   +0.199* 0.137       357     398     0.557
      40     0.642   +0.223* 0.148       585     500     0.381
     all     0.636   +0.217* 0.148       704     500     0.308

  answer alone: 0.419        * significant at 95%
```

The paired contrasts locate the knee exactly:

| contrast | mean | 95% CI | |
|---|---|---|---|
| cap 10 − cap 20 | −0.089 | [−0.175, −0.002] | **SIGNIF — 10 loses real coverage** |
| cap 5 − cap 20 | −0.113 | [−0.196, −0.030] | **SIGNIF — 5 loses more** |
| **cap 20 − uncapped** | **−0.018** | **[−0.052, +0.016]** | **null — no measured loss** |
| cap 40 − uncapped | +0.006 | [−0.002, +0.014] | null |

```
  cap 20 keeps 92% of the benefit for 51% of the tokens.
  past 20, the CI on what you gain is +/-0.03 around ZERO,
  and the bill doubles.
```

Uncapped scores marginally *below* cap 40 — not significant, but the tail is at
best inert. `_CAPS` was swept, not guessed, and 20 is where the curve flattens.

### Per-page saturation

```
  wikipedia-rust        11 fields   saturates at  5    (document type, no lift at all)
  rottentomatoes        38          saturates at  5
  sparkfun              26          saturates at  5    (page is thin regardless)
  adafruit              13          saturates at 10
  goodreads             11          saturates at 10
  coursera              71          saturates at 20
  thingiverse           26          saturates at 40
  bbcgoodfood           49          saturates at 40
```

Five of eight are done by 10. The two that need 40 are `Recipe` and a
`Product` whose useful fields sit late in the publisher's own key order — which
is the argument for a cap in the low tens rather than in the low single digits,
and against any claim that a fixed small number is safe.

---

## The run-to-run instability, stated plainly

v4 measured `answer + declared (uncapped) − answer` at **+0.083**.
v5 measures the identical construction at **+0.217**.

Same corpus, same ladder, same judge prompt, same rep count. The difference is
real and I cannot explain it away:

1. **The judge's payload set differed.** v4 scored 5 payloads per round
   including `llm_fields` and `answer_plus_llm`; v5 scored 6 that are all
   near-identical `answer+declared` variants. Blinding controls *which* arm is
   which, not what a judge does when every option looks alike.
2. **The `answer` arm itself moved** — `thingiverse` scored `ans=0.00` on one
   v5 round and `0.44` on both v4 rounds, for the same page and prompt.
3. Both intervals are wide (±0.11 to ±0.15 at n=16).

**What survives this.** The *absolute* lift of the declared path is known only
to roughly a factor of two — call it "somewhere in +0.08 to +0.22, significant
in both runs". The *shape* is what this spike measures, and shape is a
within-run paired comparison: every cap saw the same answer, the same
inventory, and the same judge call. The saturation point is not exposed to the
between-run instability, and `cap_20 − cap_all` has a tight interval (±0.034)
precisely because it is paired.

So: **trust the knee, discount the absolute number.**

---

## Limits

1. **The corpus is selected FOR declaring** (inherited from v4). This measures
   the cap given a declaration; the **declaration rate** on pages a2web
   actually fetches is still unmeasured, and it is the multiplier on the whole
   feature's value.
2. **Order under the cap is the publisher's**, not a ranking. That is deliberate
   — a2web does not rank (ADR-0012), and a ranked cap would measure the ranker.
   It also means the cap's cost is a *lower* bound on what a smarter selection
   could achieve, and an *upper* bound on how badly a naive one behaves.
3. n=16, 2 reps, Haiku.
4. Wire tokens are a `chars / 3.8` estimate. The decision turns on a ratio, so
   the constant cancels; do not quote these as exact counts.

---

## What follows

1. **Ship the declared path with a cap around 20 fields.** Measured knee: below
   it you lose significant coverage, above it you gain nothing measurable and
   pay double.
2. **Declare the truncation** — `... +N more fields declared by the page, not
   shown`. The dropped count differs from the kept count by construction, so
   unlike `hn`'s old note this one can actually fire. Without it a caller cannot
   tell "the page states only this" from "a2web stopped relaying" (ADR-0009).
3. **Keep publisher order, subject entities first.** Do not rank.
4. **Still do not ship the LLM entity block** (v3, v4). The cap does not rescue
   it — its problem is 4.6 sparse fields and 58% type instability, not volume.
5. **Next measurement is the declaration rate**, not another cap. Everything
   downstream of "when a page declares, reading it pays" is now settled; what is
   not settled is how often that antecedent holds.
