# Finding — schema-shaped extraction: research pass before proposing (2026-08-02)

Desk research for `I0269` (a2web generic core / schema-shaped extraction /
quarantined domain knowledge). Answers the four questions the inbox note said
must not be answered shallowly, plus a fifth the user raised when the note was
read back: **does shaping the output around a schema make a2web say LESS?**

No code changed. This is the input to a proposal, not the proposal.

---

## 0. The question that reframes the rest

> "one concern I have — such a shape, will it make us give less info — bc that is
> what bad. In general more information is better than less."
> — user, 2026-08-02

That concern is correct, it is the load-bearing risk, and it is **measurable**.
Everything below is organised around it.

The answer is not one answer, because "schema-shaped extraction" is two
different operations with **opposite** evidence:

```
   classify the page's entity type        shape the ANSWER around that schema
   ("this is a Product")                  ("fill name/price/brand/…")
   ─────────────────────────────          ────────────────────────────────────
   a CLASSIFICATION task                  a REASONING + RELAY task
   structure HELPS (measured)             structure HURTS (measured)
   ✅ safe to add                          ❌ this is the info-loss risk
```

Conflating them is how this becomes a regression. Keeping them apart is the
whole design.

---

## 1. Does structure reduce information? — the external evidence

**Yes, on reasoning-shaped output; no, on classification-shaped output.**

The canonical study is Tam et al., *"Let Me Speak Freely? A Study on the Impact
of Format Restrictions on Performance of Large Language Models"* (EMNLP 2024
Industry Track). Headline: a significant decline in reasoning ability under
format restriction, worse as the format gets stricter — commonly cited in the
10–30% range on reasoning-heavy benchmarks.

Two mechanisms are named in the follow-up literature, and both apply here:

1. **Premature commitment.** Constrained decoding can force the model to emit an
   answer field *before* it has finished reasoning — the structure dictates
   token order, and the reasoning has nowhere to happen.
2. **Objective competition.** Satisfying the format and generating the content
   compete for the same budget; a schema with many fields, nesting, or unions
   spends model attention on constraint-tracking that is not spent on content.

**The counter-evidence is real and must be stated, or this section is
propaganda.** The paper has been criticised for conflating *constrained
decoding / JSON-mode* (a decoder-level grammar) with *prompted structure* (a
schema described in the prompt, sampled freely). Independent replications report
JSON-mode beating unstructured generation on some tasks. And the paper's own
finding is explicitly task-dependent: **stringent formats hinder reasoning tasks
but IMPROVE accuracy on classification tasks requiring structured output.**

**What that means for a2web specifically:**

- a2web uses **prompted structure**, not constrained decoding — `EXTRACT_ROUTER_V1`
  describes a JSON envelope in the system prompt and parses the result through
  `wobble`. The harshest version of the finding (grammar-forced token order)
  does not apply.
- a2web has **already paid** the structured-output tax. It has emitted a JSON
  envelope since v0.21. The open question is not "JSON vs prose" — it is the
  **marginal** cost of one more field, which is a much smaller question than the
  literature's.
- `entity_type` is a **classification**. That is the case the literature says
  structure *improves*.

### Verdict on §1

Adding a classification field is low-risk and evidence-supported. Letting a
schema dictate the shape of `answer` is the high-risk operation, and it is the
one to refuse.

---

## 2. The internal precedent is sharper than the papers

a2web has already run this experiment, accidentally, and written it down:
`eval/findings_2026-07-11-also-here-underfires.md`.

> "the model was treating **'answered the asked question' as 'covered the
> page'** and emitting `also_here: []`."

That is **satisficing** — the model perceived its obligation as discharged and
stopped, while real page content went unrelayed. The fix was to redefine
"covered" in the prompt (`EXTRACT_ROUTER_V1` v6 → v7,
`also-here-indexes-rich-pages`).

A filled-in entity schema is a **stronger** satisficing signal than an answered
question: a form that looks complete is the most legible "I am done" cue a model
can receive. So a2web's own history predicts the failure mode, names it, and
has already had to spend a prompt revision fighting it once.

**This is the single most important input to the design**, and it is
first-party, from this codebase, on this prompt.

---

## 3. Is schema.org the right vocabulary?

**Yes, and the decision is already half-made in shipped code.**

`src/a2web/packages/structured_render.py` already parses and renders
schema.org: `ld_json`, `microdata`, `opengraph`, plus `next_data` / `nuxt_data` /
`window_var`. a2web has consumed schema.org for as long as it has had a
structured-data renderer — the decision was simply never named.

The user's memory of "some kind of XML schema standard" is **microdata / RDFa**,
schema.org's pre-JSON-LD serialisations. The vocabulary is the same; only the
encoding changed.

| candidate | verdict | why |
|---|---|---|
| **schema.org** | ✅ adopt | ~800 types; the only vocabulary with the breadth described (Product, Person, Article, Recipe, Event, JobPosting, Course, Dataset…); already consumed by `structured_render.py`; what sites actually publish |
| Dublin Core | ❌ | ~15 elements; bibliographic metadata only. No Product, no Person-as-artist |
| Open Graph | ❌ | ~5 core fields; a social-preview format, not an entity vocabulary. Already consumed as a *fallback* by `structured_render.py`, correctly |
| Wikidata / RDF | ❌ | Enormous and identifier-centric; requires a resolver and an ontology. Would import exactly the domain knowledge the note wants OUT of the core |
| vertical schemas (JSON Resume &c.) | ❌ | One domain each. N schemas = N pieces of domain knowledge in the core |

**Encoding**: JSON-LD. Microdata and RDFa are legacy for new builds in 2026;
JSON-LD is the format sites publish and the format `structured_render.py`
already prefers. Nothing to decide.

### The part that is NOT settled by "adopt schema.org"

**Is the schema a contract we validate against, or a vocabulary we suggest and
otherwise pass through?**

User's answer, 2026-08-02: **validate PRESENCE, never the VALUE.**

> "I doubt now that validation of that part is necessary, but validation of
> presence of it — necessary. even if model will fake the model — it is fine."

This is the right call and it is consistent with a rule the repo learned the
expensive way. `_recipe_md`'s allowlist omitted `recipeInstructions`, so a2web
served a recipe's ingredients and **silently dropped how to cook them**
(resolved in `lift-the-item-set-and-renderer`, 2026-08-01, by demoting the
allowlist to a label table that gates nothing). Value-validation on an open
vocabulary rebuilds that ceiling one layer up.

It also avoids a2web owning a schema registry — which would be precisely the
domain knowledge I0269 wants out of the core. **Not validating is not laziness
here; it is the architectural requirement.**

---

## 4. Does `entity_type` join `structural_form`? — and what it costs

### It is orthogonal, and the axis is genuinely missing

```
  structural_form  — what the PAGE is    listing | article | thread | product | …  (9, CLOSED)
  shape            — the DATA shape      prose | records | key-value | table | …  (7, CLOSED)
  entity_type      — what the THING is   Product | Person | JobPosting | …        (OPEN)  ← MISSING
```

Grep: `entity_type` has **zero occurrences** in `src/`. Verified 2026-08-02.

They do not substitute for each other — a `listing` of `Product`s, an `article`
about a `Person`. `structural_form=product` is the closest thing shipped, and it
is a *page* judgement ("this page is a product landing page"), not a *thing*
judgement, and it has no vocabulary behind it.

### It is NOT an envelope change — the cheapest fact found this session

`structural_form` and `shape` are consumed **internally** and are never
projected onto the wire (`src/a2web/models.py:680`, explicit comment). A sibling
field on the same boundary type inherits that.

Consequence: **`entity_type` does not touch the response envelope**, so it is
not on CLAUDE.md's Ask First list, and there is no MCP-client breakage. The note
assumed otherwise. This materially lowers the cost of the whole idea.

### The closed-enum collision, resolved

CLAUDE.md Conventions says "closed-enum verdicts for diagnostics". `entity_type`
must be **open**, or it becomes `_ENTITY_TYPES`' eight-name ceiling one layer up.

That is not actually a contradiction, because the convention is about
**verdicts** — a2web's own judgements, where an unknown value means a2web is
broken. `entity_type` is a **relayed observation** of what the page claims to
be, where an unknown value means the web is bigger than our list. Different
kind of field, different rule. The ADR should say this in one sentence so the
next reader does not re-litigate it.

The existing seam already supports it: boundary dataclasses in
`packages/llm_extract/router_payload.py` are string-typed and loose *by design*,
with the closed-enum `Literal` mirror living domain-side. An open field is the
easy case — it simply has no mirror.

### Token cost — smaller than expected

`_ROUTER_SCHEMA_DOC` measures **10,136 chars ≈ 2.7k tokens**, and v0.24
relocated it into the **cacheable `system` bucket**. So the marginal cost of an
entity block is a one-time cache write, then approximately free on every cache
hit. A ~15-line addition is roughly **+150 tokens, cached**.

**Token cost is not a real objection.** Attention dilution might still be —
which is what the spike measures.

---

## 5. The design this research points to

```
  ┌─ answer ────────────────────────────────┐   FIRST, free prose, UNCHANGED.
  │  exhaustive · faithful · neutral        │   The schema never shapes it.
  └─────────────────────────────────────────┘
  ┌─ structural_form · shape ───────────────┐   closed enums, unchanged
  ├─ entity_type   (string, OPEN)           │   ← new: presence validated,
  ├─ entity_fields (dict, passthrough)      │      value never
  └─ also_here · other_pages · obstacle ────┘   unchanged
```

Three rules, each traceable to evidence above:

1. **`answer` comes first and stays free-form.** The literature's own proposed
   mitigation is to *defer structure until reasoning is complete*; a2web's
   prompt already emits `answer` as field one. Keep it there. The entity block
   goes after.
2. **The entity block is ADDITIVE, never a substitute for `answer`.** It must
   not become somewhere the model can put content *instead of* relaying it.
   This is the §2 satisficing defence.
3. **Extra fields survive.** `discountPrice`, `couponCode`, whatever a site
   invented this quarter passes through. The generic layer is a floor, never a
   ceiling.

Rule 3 is the same rule as I0269 §5's `reason`/`anchor` carry, and the same rule
as `_recipe_md`. **Three instances, one principle, never written down once.**
That is the ADR.

---

## 6. The spike — what would actually settle it

The user's concern deserves a measurement, not an argument. Three arms, same
pages, same questions, same provider:

| arm | prompt | expectation |
|---|---|---|
| **A** control | today's `EXTRACT_ROUTER_V1` | baseline |
| **B** additive | + `entity_type` + `entity_fields` AFTER `answer` | ≈ A on answer completeness; entity block populated |
| **C** entity-primary | `answer` shaped by the entity schema | **predicted to lose** — this arm exists to make the loss visible, not to ship |

**Primary metric — answer completeness, the thing the user is worried about:**
count of distinct page facts relayed in `answer`, judged against the page. Arm B
failing to match A is the finding that kills the additive design too.

Secondary: `also_here` non-empty rate (the §2 satisficing tell — if B suppresses
`also_here` relative to A, the entity block is absorbing the index); populated
`entity_type` rate; extra-field survival rate; tokens.

Corpus: pages with a **rich body beyond the schema** — where dropping is
visible. A schema-only page (Koçtaş, 1.6k chars) cannot show the effect and
would produce a falsely clean result. Note this explicitly: it is the same trap
as `also_here`'s two-causes analysis, where an under-FETCH looked like an
under-INDEX.

Provider: `claude-code-sdk` per ADR-0016. $0 metered.

Harness: follows `eval/spikes/router_shape_v1.py` / `surface_eval_v2.py` — the
same pre-impl validation pattern that produced the router shape now shipping.

**Arm C is the point of the spike.** Without it there is no evidence that
schema-shaping *would* have hurt, only an assertion that it might.

---

## 7. The domain/site boundary audit (I0269 §4 · step 4)

Inventory of domain-specific assumptions living inside generic `packages/`.
Grepped `packages/` for commerce/recipe vocabulary, 2026-08-02.

**Site half — clean.** `handlers/` + `_manifests/handlers/`, with `tach.toml`
forbidding `packages/` → domain imports. No action.

**Domain half — one file.** Every leak is in
`src/a2web/packages/structured_render.py` (505 lines):

| site | what it is | verdict |
|---|---|---|
| `_ENTITY_TYPES` `:96` | 8-name schema.org allowlist. `Person`, `JobPosting`, `Course`, `Dataset` render as **nothing** | **the ceiling** — delete, default-keep |
| `_normalize_commerce_row` `:346` | lifts `offers.price` + `priceCurrency` → `"3690 TRY"`, `aggregateRating.ratingValue` → `rating` | domain logic in a generic package. Useful — relocate, do not delete |
| `_is_commerce_shaped` `:372` | ≥½ rows carry `price`/`url` → route to record rendering | same |
| `_RECIPE_LABELS` `:277` | label table, already demoted to gating nothing (2026-08-01) | **acceptable as-is** — a label table is a floor, not a ceiling |

The other two `packages/` hits are false positives: `prompts.py` and
`router_payload.py` mention price/brand only as *illustrative examples* in
prompt text and docstrings. Not machinery. No action.

`_RECIPE_LABELS` is the precedent for what the commerce helpers should become:
**a label/normalisation table that gates nothing.** The 2026-08-01 fix already
did this once, for the same reason, in the same file.

Note: relocating anything to or within `packages/` is on CLAUDE.md's **Ask
First** list.

---

## 8. What this implies for the proposal

Roughly three changes, not one — matching I0269's own estimate:

1. **ADR: "the generic layer is a floor, never a ceiling."** Names the rule that
   already governs `_recipe_md`, ADR-0015, the producer-claim Never-entry, and
   I0269 §5's `reason`/`anchor` carry. No code. Unblocks the other two by making
   them forced moves.
2. **Delete the `_ENTITY_TYPES` ceiling; relocate the commerce helpers.**
   Immediately fixes `Person` / `JobPosting` / `Course` / `Dataset` pages
   rendering as nothing. Independent of the LLM work.
3. **`entity_type` + `entity_fields`, gated on the spike.** Additive only.
   Presence validated, value never. Internal-only, so not an envelope change.

Open, not decided here:

- Whether `entity_fields` is a flat `dict[str, str]` or nested. Nesting costs
  format-tracking budget (§1 mechanism 2) for unclear gain — but flattening
  `offers.price` is exactly what `_normalize_commerce_row` already does, so
  there may be one shared answer here. **Worth deciding once, for both.**
- Whether the entity block should be suppressed when `structural_form=listing`
  (a listing has N entities, not one). Probably `entity_type` describes the
  ITEM type on a listing — but that is an assumption, and it should be a spike
  observation rather than a guess.

---

## Sources

- [Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models (Tam et al., EMNLP 2024)](https://aclanthology.org/2024.emnlp-industry.91/) · [arXiv:2408.02442](https://arxiv.org/abs/2408.02442) · [HF paper page, incl. the constrained-decoding-vs-JSON-mode critique](https://huggingface.co/papers/2408.02442)
- [Practical Considerations for Agentic LLM Systems](https://arxiv.org/pdf/2412.04093)
- [Learning to Generate Structured Output with Schema Reinforcement Learning](https://arxiv.org/pdf/2502.18878)
- [Schema.org — Wikipedia](https://en.wikipedia.org/wiki/Schema.org)
- [Recommended Format for Schema Markup — Schema App](https://www.schemaapp.com/schema-markup/what-is-the-recommended-format-for-schema-markup/)
- [Structured Data & JSON-LD Schema Markup in the Age of AI](https://weventure.de/en/blog/structured-data)
- First-party: `eval/findings_2026-07-11-also-here-underfires.md`;
  `openspec/changes/archive/.../lift-the-item-set-and-renderer/design.md`;
  `src/a2web/packages/structured_render.py`; `src/a2web/models.py:680`;
  `src/a2web/packages/llm_extract/prompts.py`.
