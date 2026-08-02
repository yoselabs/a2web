# Finding — entity-schema spike v2: SETTLED. The directive is the harm, not the schema (2026-08-02)

`eval/spikes/entity_schema_v2.py`, 8 pages × 3 reps × 4 arms = 24 paired rounds,
`claude-code-sdk` / `claude-haiku-4-5` (subscription, $0 metered per ADR-0016).
Raw: `eval/spikes/entity_schema_v2_summary.json`.

v1 could not attribute its own result because arm C changed two things at once.
v2 adds **arm D** to separate them, and splits the fact inventory so a correct
narrow answer stops scoring as a loss.

```
  A  control        ships today
  B  additive       entity fields AFTER answer
  D  position-only  entity fields BEFORE answer, nothing else changed
  C  entity-primary D + "do not repeat in answer what entity_fields carries"
```

---

## The result: adding the schema is free. The suppression directive is not.

**ADJACENT recall** — facts the page carries beyond the asked question. This is
the quantity the user's concern is about and the quantity ADR-0015 protects.

| contrast | meaning | mean | 95% CI | |
|---|---|---|---|---|
| **B − A** | additive fields | +0.014 | [−0.043, +0.070] | null |
| **D − A** | **position alone** | **−0.002** | [−0.046, +0.041] | **null** |
| **C − D** | **the directive alone** | **−0.026** | [−0.057, +0.005] | null (marginal) |
| C − A | position + directive | −0.029 | [−0.081, +0.023] | null |
| **C − B** | worst vs best | **−0.042** | **[−0.081, −0.004]** | **SIGNIF** |

**CORE recall** (does it still answer the question) is null for every contrast —
no arm caused a correctness regression. Highest is B at 0.936 vs A's 0.917.

**Answer length** attributes the effect cleanly, which is exactly what arm D was
built to do:

| contrast | mean chars | 95% CI | |
|---|---|---|---|
| D − A (position) | **+3.0** | [−33.5, +39.5] | null |
| C − D (directive) | **−52.8** | [−83.9, −21.7] | **SIGNIF** |
| C − A (both) | −49.8 | [−96.3, −3.3] | SIGNIF |

**100% of the shortening comes from the directive and 0% from the position.**
v1 saw only the sum (`C − A`) and could not have said this.

### So the design rule is now measured, not argued

> Add `entity_type` + `entity_fields`. Put them wherever the presence
> requirement wants them. **Never tell the model to keep `answer` short
> because the fields carry the facts.**

The schema was never the risk. The instruction to economise was.

---

## v1's index-thinning signal did NOT replicate

v1 reported `also_here` C−A = −0.67 and flagged it as the most decision-relevant
thing in the run, while noting its CI crossed zero. On 24 rounds with a fourth
arm:

| contrast | mean | 95% CI |
|---|---|---|
| B − A | +0.54 | [−0.72, +1.81] |
| D − A | +0.04 | [−0.72, +0.80] |
| C − A | **+0.29** | [−0.65, +1.23] |
| C − D | +0.25 | [−0.21, +0.71] |

Not merely non-significant — **the sign flipped**. `also_here` is noisy
(sd ≈ 2 on a mean of ~1.3) and v1's −0.67 was noise.

**Dropping the claim rather than keeping the framing it produced.** The
"satisficing absorbs the index" story was a good prediction from a real
precedent, and it is not supported. The correct summary of both spikes is that
**no measured harm to either the answer or the index was ever demonstrated** —
only to answer length, and only under the directive.

---

## Costs and defects that survive both runs

### Output tokens — the real, replicated price

| contrast | mean completion tokens | 95% CI |
|---|---|---|
| B − A | **+132** | [+90, +174] |
| D − A | **+144** | [+102, +185] |

A=163 → B=295. **~+85%**, replicating v1's +116. Completion tokens are not
cached. This is the feature's true cost, and it is the number to put in the
proposal.

### `entity_type` presence — NOT fixable by position, and that matters

The user's requirement is presence-validated. Measured presence over 24 rounds:

```
  B (after)  21/24        D (before) 21/24        C 23/24
```

v1 suggested moving the field earlier would fix B's misses. **It does not** —
D is equally imperfect. The misses concentrate on ONE page:

```
  hepsiburada-product   B: reps 1,2,3    D: reps 2,3    C: rep 2
  wikipedia-transformer D: rep 2
```

7 of 8 misses are the same page — the commerce page whose answer is trivially
complete. So this is a **page effect, not a position effect**: where the answer
is easy, the model treats the extra field as optional regardless of where it is
asked for.

**Design consequence:** presence cannot be obtained by prompt wording (the block
already says "NEVER omit this field; write `Thing`"). It must be enforced
**where the payload is parsed** — default the field to `"Thing"` when absent and
count the miss as a wobble. That satisfies "validate presence, never the value"
without a retry, and it is consistent with how the repo already handles model
wobble (`WobblePolicy.DEFAULT`).

### Open vocabulary — settled twice over

Types emitted across the three entity arms:

```
  Article · DiscussionForumPosting · DiscussionForumPost · Organization
  Product · ProgrammingLanguage · ScholarlyArticle · SoftwareApplication
  Thing · Thread · WebPage
```

Eleven distinct strings, including two that are not schema.org spellings
(`Thread`, `ProgrammingLanguage` — schema.org says `ComputerLanguage`) and one
that is a near-miss of another (`DiscussionForumPost` vs `DiscussionForumPosting`).

Two conclusions, both load-bearing:

1. **A closed enum would have been wrong**, confirming §4 of the research doc.
2. **Near-miss spellings are real**, so any consumer keying on exact type
   strings will mis-key. `entity_type` must be treated as a *hint for the
   caller*, never as a routing key inside a2web. If a2web ever branches on it,
   that branch is a closed enum wearing a string's clothes.

### Extra fields keep surviving

63 (B) / 61 (D) / 77 (C) off-vocabulary properties retained. The
floor-not-ceiling rule holds under measurement, not just precedent.

---

## What is now settled, and what is not

**Settled:**

- Adding the entity fields costs no measured answer or index content, in either
  position (`D − A` = −0.002).
- The suppression directive is the only harmful ingredient, and it must not ship.
- Open vocabulary, presence-defaulted at the parser, value never validated.
- Price: ~+130 completion tokens/call (~+85%).

**Not settled, and honestly out of this spike's reach:**

- Everything here is Haiku. A larger model may show a different (probably
  smaller) effect. Production uses Haiku, so this is the right model to decide
  on — but it does not generalise.
- `other_pages` was never measured (needs the link digest the orchestrator
  builds; a number without it would be a harness artifact).
- 24 rounds resolves ~4-6 recall points. A smaller real cost is not excluded.
- One arm-C page (`python-contact`, adjacent 0.23 → 0.08) is much worse than the
  rest. With n=3 reps that is not separable from noise, but if the directive
  ever does ship, contact/spec pages are where to look first.
