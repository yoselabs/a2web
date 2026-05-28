<!-- Canonical source: github.com/yoselabs/a2kit/blob/main/CONSTITUTION.md
     This is a verbatim copy synced manually. To propose changes, edit the
     a2kit copy first; once amended there, re-sync this file. Drift between
     the two is a bug — Article IX governs amendment. -->

# a2 Constitution

The rules above the rules. ADRs and openspec changes record individual
decisions; this document defines **how decisions are made** for the a2
ecosystem (`a2kit`, `a2web`, `a2atlassian`, `a2db`, `joi-hub`, `a2kay`,
and future siblings).

Read this **before** authoring any change that adds code, adds a
package, adopts a dependency, or grows the substrate. Cite the articles
you applied in the change's commit message or ADR.

> **Status:** draft v0.1 (2026-05-28). Iterate via ADR — amendments
> require an ADR titled `Amend Constitution: <article>`.

---

## Preamble — What this ecosystem is

The a2 ecosystem is a family of **product packages** (a2web,
a2atlassian, a2db, joi-hub, a2kay, ...) that stand on a shared
**substrate** (`a2kit` and its sibling `a2*` substrate packages).

- **Products** solve a specific human/agent need (fetch a web page,
  query Jira, run a database, store a memory).
- **Substrate** is what >1 product needs (HTTP/MCP/CLI exposure, error
  contracts, observability, lint, formatter, DI, lifecycle, plugin
  discovery).

Substrate exists to *isolate products from cross-cutting complexity*.
It earns its existence by making the next product cheaper than the
last. Products earn their existence by solving a real, named need.

The Constitution prevents the two roles from blurring.

---

## Article I — The Substrate/Product Distinction

Every line of code is either **product** or **substrate**. The
distinction is not aesthetic; it's structural and enforced by
**package layout**.

**Product code** lives in:
- `<product>/src/<product>/<domain>.py` (e.g. `a2web/fetcher.py`)
- `<product>/src/<product>/<domain>/` for multi-file domains

**Substrate code** lives in (in order of generality):
- `<product>/src/<product>/packages/<X>/` — local substrate candidate
- A standalone PyPI package (`a2<X>`) — confirmed substrate
- `a2kit/src/a2kit/packages/<X>/` — substrate tightly coupled to a2kit
- `a2kit/src/a2kit/<X>` — universal substrate every product touches

**The Two-Consumer Test.** Code is substrate if ≥2 products plausibly
need it. *Plausibly* means a named, credible second consumer — not
"someday someone might." If you can name only the current product,
the code is product-shaped today, even if it looks generic.

**Apply this article by asking, before writing any new file:**
1. Which products (named) need this?
2. If only one — does it have an obvious second consumer? If no,
   keep it in product/domain.
3. If two or more — start it under `<product>/packages/` with a
   `test_packages_independence`-style import-isolation test.

**Example:**
- `a2web/fetcher.py` (tier cascade orchestration) — product. Only
  a2web fetches web pages.
- `a2web/packages/http_cache/` — substrate candidate. a2atlassian
  and a2db could both cache typed HTTP responses.
- `a2kit/packages/formatter/` — substrate. Every product needs
  JSON/TSV wire conversion.

---

## Article II — Placement Hierarchy

Code moves through five tiers, **one tier at a time**, in either
direction:

```
Tier 1   product / domain                  (e.g. a2web/fetcher.py)
            ↓ (promote on 2nd consumer signal)
Tier 2   product / packages / <X>          (e.g. a2web/packages/http_cache/)
            ↓ (promote on confirmed substrate + OSS-gap evidence)
Tier 3   standalone PyPI <a2X>             (e.g. a2httpcache on PyPI)
            ↓ (promote on tight a2kit-core coupling)
Tier 4   a2kit / packages / <X>            (e.g. a2kit/packages/formatter)
            ↓ (promote on universal-touch evidence)
Tier 5   a2kit / <X>                       (e.g. a2kit.App, a2kit.Router)
```

**Promotion rules:**
- Always promote one tier at a time. Tier 1 → Tier 3 in one step is
  forbidden — the intermediate tier validates the boundary.
- Each promotion is recorded as an ADR or openspec change.
- Demotion is allowed and **encouraged when assumptions break**. If
  a Tier-3 package turns out to have only one real consumer after
  6 months, demote to Tier 2.

**Apply this article by asking, before promoting:**
1. Is the current tier failing? (Forces honest reason for promotion.)
2. What's the next tier's specific trigger (see Article IV)?
3. What ADR records this decision?

**Demotion is not failure** — it's the substrate refusing to lock in
a premature abstraction.

---

## Article III — Adopt Before Build

Every new package proposal **must** answer: *"What OSS already exists
for this, and why aren't we adopting it?"*

**Required research per new package:**
- Web search for the problem space (≥3 candidate libraries identified)
- Read each candidate's README + recent issues + last-release date
- For each rejected candidate: cite a *specific, non-trivial* reason
  it doesn't fit (license, abandonment, API mismatch, scope creep,
  unfixable bug). "I wanted my own" is not a reason.

**The default is adoption**, possibly with a thin wrapper. Building
from scratch requires evidence that no existing tool fits.

**When adopting:**
- Pin the version (upper bound — enforced by `REGO-PYPROJECT-UPPER-BOUND`)
- Document the adoption in the package's `_design.md` or ADR
- Treat the adopted tool as substrate-of-substrate; we wrap, we don't
  fork

**When building anyway:**
- Document the rejection of each candidate in the same place
- Note what trigger would make us reconsider adoption

**Apply this article by asking, before writing a new package:**
1. What does this problem look like? (Frame it generically.)
2. Search: what 3+ OSS libraries solve this or close?
3. For each, what's the citable reason it doesn't fit?
4. Is the answer to #3 satisfying to a hostile reviewer?

**Example failures of this article (anti-patterns):**
- Reinventing `httpx` because we wanted a different timeout default
- Reinventing `tenacity` because we didn't want a decorator
- Reinventing `structlog` because we wanted typed events (real
  problem, but the answer is "wrap structlog with typing," not
  "rewrite structlog")

---

## Article IV — Promotion Triggers

Each tier-to-tier promotion has a specific trigger. Promotion without
the trigger is premature and creates fragility.

| Promotion | Required trigger |
|---|---|
| Tier 1 → Tier 2 | A concrete second-consumer plan exists (named product + named need). Not "someday." |
| Tier 2 → Tier 3 | (a) Second consumer actually imports the package, OR (b) the package has standalone PyPI value (useful to OSS readers outside the a2 ecosystem) AND (c) Article III has been applied. |
| Tier 3 → Tier 4 | ≥3 a2-family products use the package AND it benefits from a2kit-core coupling (cannot work standalone without significant duplication). |
| Tier 4 → Tier 5 | EVERY product touches it AND removing it would break a2kit's identity. Last resort. |

**Apply this article by asking, before promoting:**
1. Which exact trigger applies?
2. What evidence supports the trigger? (Code paths, ADRs, consumer
   commits.)
3. Is there a less-irreversible alternative? (Promotion is hard to
   undo; demotion is paperwork.)

---

## Article V — Substrate Refusal

The substrate **must refuse features that don't generalize**. Refusal
is a first-class action, not a bug.

**Refusal rules:**
- A feature requested by product X that no other product plausibly
  needs stays in product X. The substrate says no.
- Refusal is recorded in the requesting product's BACKLOG (so the
  feature isn't lost), never in the substrate's BACKLOG (so the
  substrate isn't pulled toward product concerns).
- The substrate maintainer is allowed (encouraged) to say:
  "interesting problem; build it in your product. If a2atlassian also
  needs it in 6 months, we revisit."

**Anti-pattern this article prevents:**
- "Just add this one tiny option to the formatter for a2web."
- "Can a2kit have a hook for this very specific MCP behavior?"
- "Make the lint rule configurable per-project so a2web can disable it."

Each starts the substrate down the path of accreting product
opinions. Refuse early.

**Apply this article by asking, when a product requests a substrate
feature:**
1. Is this product-specific or generic?
2. If generic — what's the named second consumer?
3. If named — is the second consumer *currently asking*, or
   speculation?
4. If speculation — refuse, log in product BACKLOG, revisit if
   second consumer materializes.

---

## Article VI — Magic Budget

The substrate's consumer-facing surface uses **plain Python and
framework-native idioms**. New vocabulary is rationed.

**Rules:**
- Substrate may introduce at most **2 new consumer-facing concepts
  per minor release**. "Concept" = a new vocabulary word the
  consumer must learn to use the substrate.
- Private vocabulary (`substrate`, `finisher`, `surface`, `dispatch
  stage`, `render state`) stays internal. ADRs and internal docs can
  use it; READMEs, tutorials, and consumer-facing docstrings cannot.
- Pydantic is sacred. Substrate does not invent shorthand that breaks
  "this is just pydantic." No `a2kit.desc()`, no `a2kit.param()`,
  no custom decorator factories that hide a pydantic.Field.
- Magic that saves <3 LOC per call site is not worth introducing.

**Apply this article by asking, before adding a new exported symbol
or decorator:**
1. Can this be expressed in 1-3 lines of plain Python +
   pydantic + FastAPI / FastMCP / Click idioms?
2. If yes — don't add the symbol. Document the pattern instead.
3. If no — what's the new concept's name? Is it pythonic? Could a
   reader guess what it does from the name alone?

**Anti-pattern this article prevents:**
- Inventing private DSLs that read as DDD/Clean-Architecture cosplay
  (the Anthropologist's tribal-rejection landmine)
- Accumulating "rules to enforce the rules to enforce the rules"
  (the Physicist's self-justifying complexity)

---

## Article VII — Decisions Are Recorded

Every Constitution-grade decision is recorded — never tacit.

**Recording rules:**
- Adopting a new dependency → ADR or openspec change citing Article III
- Creating a new package (any tier) → ADR or openspec change citing
  Articles I + II + III + IV
- Promoting / demoting between tiers → ADR or openspec change citing
  Article II + IV
- Refusing a substrate feature → BACKLOG entry in the requesting
  product, citing Article V
- Adding a new consumer-facing concept → ADR citing Article VI

**Citation grammar:**
> "Per Article III, considered `httpx`, `aiohttp`, `niquests`;
> chose `httpx` because [reason]; rejected `aiohttp` because
> [reason]; rejected `niquests` because [reason]."

**Apply this article by asking, before merging:**
1. Did this change touch a Constitution article?
2. Is the article cited in the commit message / ADR / openspec
   change?
3. Could a future reader trace back the decision?

---

## Article VIII — Dependency Memory

Dependency decisions are **permanent record**. Every adoption AND every
rejection produces an ADR. The ADR is mapped to the subpackage that
owns the problem space. Re-evaluation requires finding the existing
ADR first.

**The rules:**

1. **Every dependency decision SHALL produce an ADR** — runtime,
   build-system, and dev-tool dependencies. Optional extras
   (`[project.optional-dependencies]`) are encouraged but not
   mandatory.
2. **Both adoptions AND rejections are recorded.** A rejected
   dependency is not "we didn't pick it" — it's a *citable decision*
   future readers can find.
3. **Each dep ADR SHALL be linked from the subpackage that owns the
   problem space.** The link lives in the subpackage's
   `_deps.md` file (one per package), or in the package's
   `_design.md` "Dependency decisions" section. Both adopted and
   rejected deps are listed.
4. **Before considering a dependency for an existing package**, the
   existing `_deps.md` (or `_design.md`) MUST be read. If the
   dependency has been rejected, the rejection ADR MUST be reviewed
   before any re-evaluation is proposed.
5. **Re-evaluation of a rejected dependency** SHALL produce a new ADR
   that:
   - Cites the original rejection ADR
   - Names a concrete re-evaluation trigger (one of: rejection ADR
     `last_reviewed` > 12 months ago; the library shipped a major
     version that addresses the rejection reason; the project's
     constraints have changed in a documented way)
   - Either confirms the rejection (with updated `last_reviewed`) or
     supersedes the rejection ADR with the new decision

**ADR shape for dep decisions:**

```
title: "Dep: <library> — adopted | rejected for <problem-space>"
subpackage: src/<product>/packages/<X>/        # or a2kit/packages/<X>
decision: adopt | reject
considered_alternatives: [list]
citable_reasons: [
  "library X has [issue] (URL)",
  ...
]
re_evaluation_triggers: [
  "library Y ships v2.x with [feature]",
  "we need [capability] not currently in library Z",
]
last_reviewed: YYYY-MM-DD
```

**Apply this article by asking, before adding/replacing/rejecting any
dependency:**

1. Does the relevant package's `_deps.md` already mention this
   library?
2. If yes — what does the existing ADR say? Has anything changed that
   trips a re-evaluation trigger?
3. If a re-evaluation is proposed — what's the specific trigger? Is
   it documented?
4. After the decision lands — is the ADR linked from `_deps.md`?

**Anti-pattern this article prevents:**

- The hishel pattern: a rejected dependency keeps re-appearing in
  discussions as a "fresh idea" because the rejection is folklore,
  not record. Article VIII makes the rejection a citable artifact and
  forces re-evaluation through a structured trigger gate.
- Tribal-knowledge dep choices that nobody can defend later when the
  original maintainer is busy or gone.
- Re-research cost on every minor refactor — the research is paid
  once, cached forever, refreshed only on documented triggers.

**Relationship to Article III:** Article III says "research before
building." Article VIII says "persist that research as ADR + dep-map,
forever, so it's not re-paid." III is the gate before building; IX is
the institutional memory that prevents re-litigation.

---

## Article IX — Self-Application

The Constitution applies **automatically**. Every article in this
document SHALL have a corresponding **mechanical check** — a Rego
policy, lint rule, pre-commit hook, ADR/openspec template gate, or
named agent skill. An article without a mechanical check is draft, not
enforced; it sits in the Enforcement Inventory (below) marked
`[pending]` and does not bind until built.

**Three enforcement layers, in order of precedence:**

1. **Mechanical checks** — fail-closed CI gates. A change that violates
   an enforced article fails `make lint` or pre-commit and cannot land.
   No agent or human can override without amending the article.
2. **Agent skills** — AI agents working in any a2-ecosystem repo SHALL
   invoke the `constitution-check` skill before proposing any
   substrate-touching change. The skill classifies the change, runs the
   mechanical checks, drafts required artifacts (ADR / adoption
   research / BACKLOG entry), and either:
   - **proceeds** if the change is compliant
   - **drafts** the recordable artifact if a Constitution-grade
     decision is needed (Article VII)
   - **refuses** with article citation if a non-recoverable violation
     is detected
3. **Human gate** — required only when (a) an agent escalates a
   conflict it cannot resolve under existing articles, or (b) the
   Constitution itself is being amended (see Amendment section).

**Autonomy gradient.** Human involvement decreases as the system
proves itself through observed compliance:

| Phase | Human role | Transition criterion |
|---|---|---|
| **A** (current) | Approves every Constitution-touching change. Agents apply, draft, propose; human signs off each. | Default starting state. |
| **B** | Approves only article amendments + flagged violations. Routine compliant changes auto-merge. | After 3-6 months of Phase A with zero false-positive refusals + zero compliant-but-blocked changes. |
| **C** | Approves only article amendments. Everything else runs autonomously; agents refuse non-compliant work without escalation. | After 12+ months of stable Phase B + clean track record on refusal accuracy. |

Phase transitions are themselves Constitution-governed — amending the
Constitution to grant more autonomy requires evidence of track record
recorded as an ADR.

**Apply this article by asking, when authoring any new Constitution
article or amendment:**

1. What's the mechanical check that enforces this article?
2. If no mechanical check is feasible — can the article be
   restructured so it becomes checkable? If not, it's guidance, not
   constitution; relocate to a separate guidance doc.
3. Does the `constitution-check` skill know how to handle this
   article? If no, mark `[pending]` in the Enforcement Inventory and
   schedule the skill update.
4. What's the precedence if mechanical check and agent skill disagree?
   (Default: mechanical check wins.)

**Anti-pattern this article prevents:**

- "Aspirational" constitution articles that everyone agrees with but
  nobody enforces — the architectural equivalent of "we should write
  more tests."
- AI agents drifting toward locally-easy solutions because the
  Constitution is "guidelines." Mechanical enforcement makes drift
  fail closed.
- Constitution evolution that outpaces the enforcement layer —
  articles must be built mechanically BEFORE they bind.

---

## Enforcement Inventory

Each article's current enforcement state. Articles marked `[pending]`
are draft per Article IX and do not bind until their mechanical
check is built.

| Article | Mechanical check | Skill | Status |
|---|---|---|---|
| **I** Substrate/Product | `test_packages_independence` import-isolation test per package; `REGO-PACKAGE-BOUNDARY` | `classify-change` | `[pending]` (a2web has the test; a2kit-wide rollout pending) |
| **II** Placement Hierarchy | `REGO-TIER-PROMOTION` — file move between tiers requires linked ADR; pre-commit detects moves | `promotion-detector` | `[pending]` |
| **III** Adopt Before Build | New `packages/<X>/` requires `_adoption_research.md`; `REGO-ADOPTION-RESEARCH` | `adoption-research` (auto web-search + draft) | `[pending]` |
| **IV** Promotion Triggers | ADR template requires "trigger evidence" field; `REGO-PROMOTION-TRIGGER` validates ADR shape | `promotion-validator` | `[pending]` |
| **V** Substrate Refusal | `REGO-SUBSTRATE-BACKLOG-PURITY` — substrate BACKLOG entries must name ≥2 products | `refusal-router` (auto re-files in product BACKLOG) | `[pending]` |
| **VI** Magic Budget | Per-release diff of exported symbols; `REGO-MAGIC-BUDGET`; `REGO-VOCAB-LEAK` (private vocab in consumer-facing docs) | `vocab-auditor` | `[pending]` |
| **VII** Decisions Recorded | Commit-message hook: substrate-touching commits cite article(s); `REGO-CONSTITUTION-CITATION` | `citation-checker` | `[pending]` |
| **VIII** Dependency Memory | Per-subpackage `_deps.md` presence check; `REGO-DEP-ADR-LINK` validates each dep has ADR + subpackage mapping; ADR template requires `decision`/`considered_alternatives`/`re_evaluation_triggers` fields | `dep-research` (auto-search OSS + draft adopt/reject ADR + update `_deps.md`) | `[pending]` |
| **IX** Self-Application | This Enforcement Inventory itself; CI gate that fails if any non-`[draft]` article lacks an enforcement entry | `constitution-check` (entrypoint that dispatches all the above) | `[pending]` (chicken-and-egg — will be Phase-1 of the enforcement layer) |

**Phase tracker:** currently **Phase A** (Article IX). Phase
transitions are recorded as amendments to this table with the
supporting evidence ADR.

---

## How AI agents apply the Constitution

The formal rule is Article IX (Self-Application). This section is the
**practical workflow** for the current Phase A (human-confirmed) state.

When an AI agent (Claude Code, Cursor, etc.) is asked to make any
non-trivial change in any a2-ecosystem repo:

1. **Invoke `constitution-check`** before drafting code. (Once the
   skill exists; until then, the agent reads this file and self-applies
   the article checklists.)
2. **Classify the change**: which articles apply?
3. **Run the mechanical checks** for each applicable article.
4. **Draft any required artifacts** — ADR / adoption research /
   BACKLOG entry — citing the articles.
5. **Refuse with citation** if a non-recoverable violation is detected.
6. **Cite the articles** in commit message / PR description / ADR.
7. **Escalate to human** only when (a) two articles conflict and the
   resolution is non-obvious, or (b) the requested change requires
   amending the Constitution.

Phase A means: human signs off each Constitution-touching change.
Phase B will auto-merge compliant changes. Phase C lets agents refuse
non-compliant work without escalation.

The Constitution is the agent's North Star. Without enforcement,
agents drift toward whatever solution requires the fewest local
objections — which is exactly how substrate accretes product
complexity. Mechanical enforcement makes drift fail closed.

---

## Amendment

The Constitution is not sacred. It's a current-best-guess at how to
keep the substrate honest. Amend it via ADR titled
`Amend Constitution: <article>`. Amendments record:
- What changed
- Why the previous rule failed (or no longer applies)
- What new behavior the amended article enforces

---

## See also

- `AGENTS.md` — tool-agnostic conventions for working in a2kit
- `CLAUDE.md` — Claude-specific overlay on AGENTS.md
- `docs/adr/INDEX.md` — recorded decisions
- `docs/PROMOTION_AUDIT.md` — first applied audit (2026-05-28) ranking
  every a2kit + a2web package against Articles I-IV
- `openspec/changes/` — proposals in flight
- `BACKLOG.md` — deferred work (substrate refusals land here in the
  requesting product, never in a2kit's own BACKLOG)
- Per-subpackage `_deps.md` files — Article VIII dependency decisions
  (example: `src/a2kit/packages/formatter/_deps.md`)
