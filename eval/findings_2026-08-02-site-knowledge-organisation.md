# Finding — I0269 part 2: where site/service knowledge belongs (2026-08-02)

The second half of `I0269`: *"HN, Reddit, GitHub, arXiv, Wikipedia, Discourse,
Habr, V2EX, Twitter tricks must stay encapsulated."*

The note's own read was that the **site** half is already in decent shape
(`handlers/` + `_manifests/handlers/` + `tach.toml`) and the **domain** half
(commerce/recipe logic inside `packages/`) is not. Both halves are checked here
against the code and against the outside literature, and the ablation measures
what the site half is actually worth.

---

## 1. The site half is already the industry pattern — at 1/200th the scale

**yt-dlp** is the reference implementation of "organisation per website/service":
**1800+ extractors**, one class per site (or site family), a `_VALID_URL` regex
per extractor for dispatch, and a lazy-loading registry so 1800 modules do not
cost 1800 imports at startup.

a2web's handler layer is the same design, arrived at independently:

| yt-dlp | a2web |
|---|---|
| `InfoExtractor` subclass per site | `Handler` protocol per site (`handlers/*.py`) |
| `_VALID_URL` regex | `matches(url, settings)` + the anchored-URL-regex rule (`test_handler_markup_funnel.py`) |
| `_extractors.py` / `lazy_extractors.py` registry | `_manifests/handlers/*.py` + `load_surface` |
| one file per site | one file per site |

**So "encapsulate the site tricks" is not work to be done — it is work already
done**, and the pattern it matches is known to scale two orders of magnitude
beyond a2web's nine. That is the honest answer to I0269 §4's site half, and it
is stronger than the note's "in decent shape".

### Where a2web differs — and it is the important difference

yt-dlp's extractor **is** the capability: no extractor, no download. `GenericIE`
exists but is weak for most sites. So yt-dlp must treat breakage as an outage,
and it maintains a **generated `supportedsites.md` carrying per-site status,
including "Currently broken"**.

a2web has a strong generic path (`raw`/`jina`/`browser` + LLM extraction) that
runs when a handler misses. **A a2web handler is an optimisation, not a
dependency.** This is a structurally better position, and it changes what the
organisation must guarantee:

```
  yt-dlp    must PREVENT rot          (rot = capability lost)
  a2web     must DETECT rot           (rot = quality lost, silently)
            and PROVE the fallback
```

The risk a2web actually carries is therefore not "the handler broke" but **"the
handler broke and nobody noticed, because the generic path kept answering"** —
a quality regression wearing a success's clothes. That is the ADR-0009 harm
shape one layer down, and it is what the organisation should be built against.

---

## 2. The wrapper-maintenance literature names a2web's exact gap

Lerman, Minton & Knoblock (*Wrapper Maintenance: A Machine Learning Approach*,
JAIR 2003) split the problem in two:

- **verification** — detect that a wrapper stopped extracting correct data;
- **reinduction** — automatically rebuild it.

Their verification works by learning the *syntactic patterns of the extracted
data* and flagging a statistically significant distribution shift. Reported:
35 of 37 real wrapper changes caught, precision 0.73 / recall 0.95.

Mapping onto a2web:

| literature | a2web today |
|---|---|
| verification (structural) | ✅ `dom_schema`'s `ROT` verdict — the schema no longer matches |
| verification (quantitative) | ✅ **`handler_probe.py`'s declared yield floors** — a content floor and a candidate floor per probed URL shape |
| verification (distributional) | ❌ absent |
| reinduction | ❌ absent — correctly so, that is ML infrastructure far outside scope |

**a2web is further along here than the note assumed, and the middle row is why.**
`handler_probe.py` does not merely ask "did it return something" — that was the
bug it was rebuilt to fix, because `## Papers (0)` is non-empty prose. Each probe
case declares the **yield** a working handler produces at that URL, floors are
set deliberately BELOW observed values (a floor pinned at today's number is a
golden that fails on content rotation instead of rot), every manifest handler
must have a case, and `tests/capabilities/site_handlers/test_probe_case_table.py`
guards the table offline in `make check` so a floor cannot be quietly zeroed to
turn a red probe green.

That is a real, if crude, quantitative verifier — a count-versus-floor check
rather than Lerman's learned distribution.

**The residual gap is narrower than "no verification":** floors catch *too few*
rows. They cannot catch *the wrong rows* — a parser returning the right NUMBER of
plausible-but-wrong records passes every floor. a2web's July incident was the
catchable kind (arXiv and wikipedia parsers returning **zero** rows against pages
holding 47 entries and 1066 anchors). The wrong-rows kind has simply not been
looked for, and Lerman's syntactic-pattern check is the known technique for it.

**The other gap is cadence, not capability.** The probe is live-network and
on-demand (`make handler-probe`, `Makefile:167`), so per-handler status exists
but is never *published* — nobody learns a handler went red until someone runs
it. That is the piece yt-dlp's generated `supportedsites.md` covers and a2web
does not.

Note also the shape of their result: **recall 0.95, precision 0.73** — the
verifier over-warns. That is the same false-positive asymmetry a2web already
chose deliberately for walls vs empties (a false wall over-warns cheaply; a
false empty is a confident silent miss). The literature reached it independently,
which is mild evidence the asymmetry is right rather than a local preference.

### And the 2026 answer is not "hand-write more wrappers"

*Co-Scraper* (arXiv 2606.14821, June 2026) synthesises a reusable XPath wrapper
from three query-pruned seed pages, using a fine-tuned small model, explicitly to
**amortise LLM cost** across repeat fetches of one site. *AutoScraper* (2404.12753)
is the earlier form.

This is worth knowing but is **not** what a2web should do next: synthesised
wrappers still break, so it buys cheaper *creation* while leaving *maintenance*
— the half a2web is actually missing — untouched. Filed as context for a later
decision, not as a recommendation.

---

## 3. The `reason` carry (I0269 §5) — the rule as written cannot be implemented

I0269 §5's table is **accurate**; verified at the call sites:

| handler | `reason` | site |
|---|---|---|
| arxiv | the author list | `arxiv.py:334` |
| hn | `142 points, 88 comments` | `hn.py:238` |
| github | `issue · 12 comments` / `PR · N comments` | `github.py:358,386` |
| discourse | `47 replies` | `discourse.py:238` |
| reddit | a humanised age | `reddit.py:654` |
| wikipedia | `related article` | `wikipedia.py:203` |
| habr, v2ex | *(none — no `next_links`)* | — |

So six handlers do carry real site-specific signal, and converging them onto one
generic label would destroy it. That part of §5 holds.

**But its refinement does not survive contact with the code.** §5 says the
fallback must test *presence, not emptiness* — `reason if the producer supplied
one else generic`, never `reason or generic`. Two problems:

1. **The type forecloses it.** `NextLink.reason` is `str` (`models.py:157`),
   required, no default. There is no representable difference between "the
   producer supplied nothing" and "the producer supplied an empty string". The
   presence test §5 specifies **cannot be written** against today's model.

2. **The one empty in the codebase is accidental, not deliberate.** Reddit emits
   `human_age(...) if e.epoch else ""` — the `""` is a *degradation* when the
   timestamp is missing, not a considered choice to say nothing. Preserving it
   verbatim (which is what §5's rule instructs) would ship a blank `reason`
   where a generic label would genuinely be better.

**Corrected call:** the fix is not a smarter fallback rule, it is making absence
representable — `reason: str | None`, with reddit emitting `None` when `epoch` is
missing. Then "presence, not emptiness" becomes meaningful instead of accidental,
and §5's rule is implementable exactly as intended.

This is a small change and an easy one to get wrong in the other direction, so
it is worth stating plainly: **§5's principle is right; its mechanism as written
is not yet buildable.** Found by opening the call sites rather than by trusting
the note's table — the same discipline `enforcement-integrity` now requires.

---

## 4. The domain half — the audit

Confirmed 2026-08-02 by grepping `packages/` for commerce/recipe vocabulary.

**Site half: clean.** No action. `tach.toml` forbids `packages/` → domain
imports and the boundary holds.

**Domain half: one file.** Every leak is `packages/structured_render.py`:

| site | what it is | verdict |
|---|---|---|
| `_ENTITY_TYPES` `:96` | 8-name schema.org allowlist; `Person`/`JobPosting`/`Course`/`Dataset` render as **nothing** | the ceiling — demote to a label table (ADR-0018). **But measured cost is small: 2 dropped types over 26 pages** (`entity_type_ceiling_probe`). Do it on principle + asymmetry, not on a claimed pile of losses |
| `_normalize_commerce_row` `:346` | lifts `offers.price` + `priceCurrency` → `"3690 TRY"`, `aggregateRating.ratingValue` → `rating` | domain logic in a generic package. **Useful — relocate, never delete** |
| `_is_commerce_shaped` `:372` | ≥½ rows carry `price`/`url` → route to record rendering | same |
| `_RECIPE_LABELS` `:277` | label table, already demoted to gating nothing (2026-08-01) | **already correct** — this is the model the other two should follow |

The two other `packages/` grep hits (`prompts.py`, `router_payload.py`) are
false positives: price/brand appear only as illustrative examples in prompt text
and docstrings. Not machinery.

`_RECIPE_LABELS` is the precedent: the 2026-08-01 fix already converted one
allowlist-gate into a label-table in this exact file, for this exact reason.

---

## 5. What settles, and what the organisation should actually change

**Settled:**

- The site half needs no reorganisation. It is the yt-dlp pattern, validated at
  200× the scale, and `tach.toml` already enforces the boundary I0269 asks for.
- The domain half is one file and four call sites, with an in-file precedent for
  the fix.
- The real exposure is **undetected handler rot masked by a working generic
  path** — not insufficient encapsulation.

**Therefore the organisation work is not "isolate more". It is, in order:**

1. **Make rot loud in-process.** `handler_schema_rot` is emitted by only 3 of 9
   handlers (`arxiv`, `reddit`, `wikipedia`). Verified: `github`, `hn`, `habr`,
   `v2ex`, `discourse`, `twitter` contain **zero** `log_warning`/`log_info`/
   `log_error` calls — they return `None` or `empty_result(...)` silently. The
   probe catches this **when run**; production never says a word.
2. **Prove the fallback.** The ablation is the first evidence that disabling a
   handler still yields an answer. That property is currently incidental —
   nothing tests it, and it is the entire reason a2web can tolerate rot at all.
3. **Publish per-handler status on a cadence.** Not a new probe —
   `handler_probe.py` already has the hard part (declared yield floors, offline
   table guard). What is missing is that it runs on demand only, so a red
   handler stays unnoticed. This is yt-dlp's `supportedsites.md` lesson applied
   to an artifact a2web already owns.
4. **Classify each handler by what it provides** (retrieval / rendering /
   indexing / redundant), because those deserve different maintenance budgets
   and the current organisation cannot express the difference.

Item 4 is what the ablation measures, and its results follow.

---

## 6. Ablation results

> Filled from `eval/spikes/handler_ablation_v1_summary.json`.

See `findings_2026-08-02-handler-ablation.md`.
