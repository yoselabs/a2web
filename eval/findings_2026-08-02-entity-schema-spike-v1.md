# Finding — entity-schema spike v1: the predicted harm did not appear (2026-08-02)

`eval/spikes/entity_schema_v1.py`, 8 pages × 3 reps, `claude-code-sdk` /
`claude-haiku-4-5` (subscription, $0 metered per ADR-0016). Raw:
`eval/spikes/entity_schema_v1_summary.json`.

Tests the concern the user raised against `I0269`: **does shaping the output
around a schema make a2web say less?**

```
  A  control       EXTRACT_ROUTER_V1 verbatim (ships today)
  B  additive      entity_type + entity_fields AFTER answer
  C  entity-first  same fields BEFORE answer + "do not repeat them in answer"
```

---

## The headline: I predicted C would lose answer content. It did not.

`findings_2026-08-02-schema-shaped-extraction.md` §1–2 argued from the
satisficing literature and from a2web's own `also_here` under-fire that arm C
would cost measurable answer content. **Measured, it did not.**

| paired delta (within page + round, n=21) | mean | 95% CI |
|---|---|---|
| recall **B − A** | +0.002 | [−0.057, +0.061] |
| recall **C − A** | −0.018 | [−0.073, +0.037] |

Both intervals contain zero. The honest statement is not "no effect" but **"no
effect larger than about 6 points of recall"** — that is all this sample can
exclude. A smaller real cost would not have been seen.

**Recording the prediction as unconfirmed, not quietly keeping the conclusion it
implied.** The design that follows is now justified by the presence and token
results below, not by an answer-loss result that did not materialise.

---

## What actually moved

### 1. Output tokens — the one large, unambiguous cost

| paired delta | mean | 95% CI |
|---|---|---|
| completion tokens **B − A** | **+116** | [+63, +169] |
| completion tokens **C − A** | **+120** | [+72, +168] |

A=157 → B=273 completion tokens: **+74%**, in 17 of 21 rounds.

**This corrects the previous findings doc.** It said "token cost is not a real
objection", reasoning from the *input* side — the schema block rides in the
cacheable system bucket, so prompt cost is a one-time cache write. That reasoning
was right about input and silent about output. **Completion tokens are not
cached and are the expensive direction.** The entity block costs ~120 output
tokens on every call, cache hit or not.

That is the real price of this feature. It is a defensible price for a populated
entity index, but it must be stated as the cost, not waved past.

### 2. `entity_type` presence — arm B is unreliable exactly where B is easiest

The user's stated requirement is **presence validated, value never**. Measured
presence:

```
  B (after answer) : 18/21 rounds     <- missing all 3 hepsiburada reps
  C (before answer): 21/21 rounds
```

B dropped the field on all three reps of the **one page whose answer was
trivially complete** (hepsiburada, recall 1.00 for every arm). That is the
additive design's genuine defect: a field placed after a satisfying answer is a
field the model treats as optional. It is also the single strongest argument for
C's ordering, and it arrived from the measurement rather than the prior.

### 3. The same-page index — directional, NOT established

| paired delta | mean | 95% CI | W/T/L |
|---|---|---|---|
| `also_here` **C − A** | −0.67 | [−1.47, +0.14] | 2/13/6 |
| `also_here` **B − A** | 0.00 | [−0.82, +0.82] | 3/16/2 |

C roughly halves the index (A mean 1.29 → C 0.62) and C's answers are
significantly shorter (−48 chars, CI [−83, −12]). But **the index interval
crosses zero**, so this is a direction, not a finding. It is the most
decision-relevant thing in the run and the sample cannot settle it — which is
what v2 is for.

If it is real it matters a lot: it would mean C's harm is not in the `answer` at
all but one field over, in the ADR-0015 index — a2web withholding the body
*and* thinning the map of what it withheld.

### 4. Open vocabulary — vindicated, decisively

Types emitted across 7 pages: `Article`, `DiscussionForumPosting`,
`Organization`, `Product`, `ProgrammingLanguage`, `ScholarlyArticle`,
`SoftwareApplication`, `Thing`, `Thread`, `WebPage`.

**Nine distinct types on seven pages**, several outside any plausible fixed
list, and two (`Thread`, and `ProgrammingLanguage` where schema.org says
`ComputerLanguage`) not schema.org spellings at all. `_ENTITY_TYPES`' eight-name
allowlist would have discarded or mangled a large share of this. `Thing`
appeared as the intended escape hatch and behaved.

A closed enum here was not a stylistic preference to argue about. **It would
have been wrong on this evidence.**

### 5. Extra fields survive — the `couponCode` case, confirmed

42 (B) and 46 (C) off-vocabulary properties kept, including:

```
  firstStableRelease   pythonRequirement   webmaster_email   arxivId
  latestPrerelease     developmentStatus   support_forum     dateFirstAppeared
  implementationLanguage  firstPublicRelease  creationYear   isPartOf
```

These are exactly what a fixed schema would have dropped: site-invented,
domain-specific, and useful. The floor-not-ceiling rule is confirmed empirically,
not just by the `_recipe_md` precedent.

---

## Two flaws in v1, named because they bound the conclusions

### A. Arm C confounds two changes

C moved the entity block **and** added "do not repeat in `answer` what
`entity_fields` carries". The shorter answers and the thinner index could come
from either. **v1 cannot attribute them**, so it cannot say whether leading with
the type discriminator is itself harmful — which is the actual I0269 §2
question.

Fix: **arm D** — entity block before `answer`, *no* suppression directive. D
isolates position; C then measures the directive.

### B. Two of seven pages had no discriminating power

```
  hepsiburada-product     recall 1.00 for every arm, every rep   (ceiling)
  wikipedia-rust-narrow   recall 0.13-0.20 across the board      (floor)
```

The floor case exposes a **metric artifact**: the inventory asks for facts "a
reader who asked this question would want", which is broader than the question.
A correct narrow answer therefore scores low by construction. This is fair
between arms (all three face the same inventory), so the paired comparison
stands — but it burns power, and the effective n is well below 21.

Fix: split the inventory into **core** (facts that answer the question) and
**adjacent** (facts the page carries that a reader would want alongside).
Adjacent recall is the better instrument anyway — *it is the quantity the user's
concern is actually about*, and the same quantity ADR-0015 exists to protect.

### Also: one page lost

`github-ruff` died on `LLMTimeout` after 180s and is absent from all statistics.

---

## Where this leaves the design

Unchanged and now evidence-backed:

- **Open vocabulary, presence validated, value never.** §4 is decisive.
- **Extra fields survive.** §5 is decisive.

Changed by the measurement:

- **The cost is ~120 output tokens per call, not ~0.** State it in the proposal.
- **Placing the entity block after `answer` does not guarantee presence** (18/21).
  The additive design as sketched in the previous findings doc does not satisfy
  the user's own presence requirement. Either the field moves earlier, or the
  prompt must make it non-optional some other way.

Still open, and the reason for v2:

- Does leading with the type discriminator cost the index? (confounded in v1)
- Is the `also_here` drop real? (directional, CI crosses zero)

Nothing here justifies shipping yet. It justifies a v2 that can answer those two.
