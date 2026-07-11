## Context

a2web's `ask` tool fetches a page, runs a small server-side extractor LLM over the content, and returns a lean answer plus follow-up hints (`ask_here` same-URL questions, `try_url` different-URL drilldowns).

**The originating failure.** On a Hepsiburada product page, an agent asked "summarize the reviews." Reviews live on a **separate** URL (`…-yorumlari`). a2web returned `obstacle: empty`, `retrieval_incomplete: true`, "no reviews here — visit the reviews section" — correct and honest (ADR-0009 working). But it could **not** return the reviews URL. Its `try_url` was a **wrong guess** (a SKU-variant product URL lifted from JSON-LD `offers.url`). The calling agent only recovered by *itself* guessing Hepsiburada's `-yorumlari` convention.

**Why it was blind (probe-verified).** The extractor is fed `assemble_menu(content_candidates)` = trafilatura prose + JSON-LD synth. Probes on the real pages:
- `trafilatura.extract(...)` is called **without** `include_links` → strips **all** hrefs; keeps only anchor text.
- Even `include_links=True` does **not** recover the reviews link — trafilatura removes the whole nav/tab element as boilerplate *before* links matter.
- The reviews href survives **only** in the separate selectolax `links[]` pass (role-classified, ~250 entries on a mega-menu page, never fed to the extractor).
- `try_url`'s "must appear verbatim in content" instruction is therefore **impossible to satisfy** (links aren't in the content) and **unenforced** → the model guesses.

So this is **structural blindness, not fabrication**. The fix is to let the extractor see the real links and hand one back safely.

**Constraints.**
- No per-site rules / URL-scheme guessing (`-yorumlari`, `6→7` id bumps) — a maintenance trap the user explicitly refuses.
- Quality is non-negotiable; token savings must not degrade answer quality.
- `content_extract` is **shelf-adopted** — changing its trafilatura call or link-gate needs a config passthrough or a shelf contribution, not a local edit. **Shelf-loop finding (see D13): v1 needs none of that.** The selectolax `links[]` pass already flows into a2web (`fetcher.py:251` → `fc.links`) with footer/nav/tab roles intact, so the reviews anchor is already in hand; the two shelf-touching items are deferred EVOLVEs, not blockers.
- Dev/eval LLM budget: never metered Anthropic direct; OpenRouter / subscription only.

## Goals / Non-Goals

**Goals:**
- Let the extractor **see the page's real links** (in-body + chrome) and return the correct sub-resource/continuation URL — generically, zero per-site rules.
- Never fabricate or guess a URL: only real anchors reach the caller (closed-set rehydration).
- Keep the token cost tiny and on the cheap extractor model; never increase output tokens vs. today.
- Make suggestions **genre-aware and neutral** without a maintained genre table.
- Preserve all product invariants (ADR-0009 loud incompleteness; ADR-0012 no manufactured selection).

**Non-Goals:**
- Deterministic relevance filtering of links (proven impossible across marketplaces — the LLM judges).
- Per-site handlers for marketplaces (last resort only; not in this change).
- Deciding the `try_url`/`next_links` consolidation (deferred — see Open Questions).
- Executing JS to reveal purely client-rendered links (out of scope; browser tier already exists for escalation).

## Decisions

Each decision records the choice, the rationale, and the **rejected** alternatives with why — per the request to preserve history. Decisions marked **[ADR-worthy]** should be promoted to a top-level a2web ADR at apply time (they encode durable product/architecture posture); the rest are change-local.

### D1 — Feed links to the extractor from **two sources**, unioned **[ADR-worthy]**
- **Choice:** `trafilatura(include_links=True)` for **in-body** links (kept in place, with surrounding prose for positional grounding) + selectolax `links[]` **minus** the in-body set for out-of-body chrome (nav/footer/tab). Union feeds the extractor menu.
- **Why:** in-body links carry context ("see the `[reviews]` **before buying**") the model reasons over; the reviews *tab* is chrome and lives only in selectolax. Probe-confirmed: `include_links=True` keeps `[label](url)` for in-body anchors but still drops the footer/nav reviews link, which selectolax keeps. The union loses nothing.
- **Rejected:**
  - *trafilatura `include_links` alone* — drops the reviews tab (element-level boilerplate removal). Verified.
  - *selectolax digest alone* — loses positional grounding for in-body links.
  - *Inline the chrome links into prose deterministically* — **impossible**: trafilatura already deleted the element, so there is no anchor position to reattach to; would require an LLM to decide placement (the runtime cost we avoid).

### D2 — Encode links as `{{n}}` placeholder handles; server rehydrates (closed-set) **[ADR-worthy]**
- **Choice:** each surviving link → `{{n}}` (numeric, delimited) + anchor label + trimmed path (domain shown only if off-domain). The extractor emits **handles**; the server maps handle → real href via a closed-set table. Unknown handles are dropped.
- **Why:** (a) input trim (URL is the expensive part; label is the cheap semantic handle); (b) output trim (model emits `{{3}}`, not a 100-char URL — output tokens are pricier); (c) **correctness** — a model can't hallucinate a URL it never types; a handle not in the table is rejected, closing the exact hole that produced the wrong guess. The ID replaces the URL on **output**, not input, so URL signal for judgment is preserved.
- **Eval evidence (adversarial, temp 0):** content with products literally named "Sony WH-**L7**", "Xiaomi **L1**", raw SKU "HBCV0000ATJ8M2".
  - All schemes preserved handles and names at the **model** level on Haiku 4.5, gemini-2.5-flash, **and DeepSeek V4 Flash (server default)** — model behavior is not the differentiator.
  - **Rehydration** is the differentiator: closed-set regex on bare `L1` **corrupted** "Xiaomi **L1** Desk Lamp" → replaced the in-name "L1" with a URL. Every **delimited** scheme (`{{n}}`, `⟦n⟧`, `⟦urln⟧`) was collision-clean.
- **Rejected:**
  - *Bare `L1`/`L2`* — collides with real model names/SKUs at the rehydration layer. **Eval-demonstrated corruption.**
  - *`[L7]` (markdown brackets)* — collides with markdown link/reference syntax.
  - *Prefixed `{{url7}}`* — no measured benefit; both models understood bare-numeric `{{7}}` from a one-line instruction; the prefix only adds tokens.
  - *`⟦n⟧` (math brackets)* — collision-safe but non-ASCII for no benefit over ASCII `{{n}}`; kept as fallback only.
  - *Anchor-label only (drop URL entirely)* — **quality loss, probe-quantified**: ~40% of a real page's anchors had non-unique labels ("Tüm Kategoriler" ×4) where only the URL disambiguates, and page-*type* often lives only in the URL ("Hepsiburada" label = a seller store). Label-only would degrade judgment.

### D3 — **Safe deterministic cuts only**; LLM does all relevance judgment **[ADR-worthy]**
- **Choice:** drop only provably-same-document or unfetchable links — self-link, `#fragment`-only, trailing-slash/normalization dup, `javascript:`, exact-dup href. Everything else is fed to the model. The `{{n}}` encoding is what makes "pass ~all links" affordable (~200 links ≈ ~1.4k Haiku-input tokens).
- **Why:** relevance ("is this the reviews page?") cannot be judged deterministically across marketplaces without per-site rules. Cheap encoding dissolves the need to filter. The `#fragment` rule *also* auto-drops the false-positive inline "tab" (same-document, not separately fetchable) while keeping the real distinct-URL reviews link.
- **Rejected:**
  - *Relevance filtering to ~15 "good" links* — smuggles undecidable relevance judgment into a deterministic filter; would drop the good link or need site rules.
  - *Role-based dropping (drop `nav`/`footer`)* — unreliable: the mega-menu is tagged `primary` (not in a semantic `<nav>`), and footer-dropping kills `mailto:`/`tel:` (see D4).

### D4 — Retain `mailto:` / `tel:`; they are data, not navigation
- **Choice:** never drop `mailto:`/`tel:` (any DOM role); surface the raw href value (not placeholdered — the value IS the payload); for label-less contact anchors, derive the label from the href.
- **Why:** probe-verified — trafilatura destroys contact links in **both** configs (footer boilerplate); they survive only in selectolax; and the selectolax `if href and anchor` gate **drops** a label-less `<a href="mailto:…"></a>` (the address-only-in-href case). The answer to "what's their email" *is* the href.
- **Rejected:** *treat `mailto:`/`tel:` as droppable schemes* (my initial position) — eval/probe showed it deletes the only copy of the contact info.

### D5 — Dedup **by target**, unioning labels (not drop)
- **Choice:** when one href is reached by several labels, collapse to **one** handle whose label is the **union** of the distinct labels.
- **Why:** the multiple framings ("Gillette Proglide" | "Tıraş Makinesi" | "En çok satan") tell the model the page answers multiple areas — *adds* signal while removing duplicate handles/paths.
- **Rejected:** *drop duplicates* — discards the extra labels' semantic signal.

### D6 — Suggestions are **genre-aware via a principle**, not a maintained table **[ADR-worthy]**
- **Choice:** the prompt carries the principle *"surface links that extend the page's primary entity — deeper detail · community signal · transaction terms · sibling/parent entities,"* plus 1–2 worked examples explicitly marked non-exhaustive. Per-genre expectations ("product pages should surface reviews") live in the **eval corpus** as tests.
- **Why:** the Hepsiburada failure was never "the model doesn't know products have reviews" — Haiku has that world knowledge; it never saw the link (D1 fixes that). A principle generalizes to genres never enumerated; a table is a maintenance trap and creates **slot-filling pressure** (binds the closest-looking link to each expected slot — and closed-set validation stops *fake* URLs, not *wrong real* ones, so label→intent misbinding becomes the dominant error). (Fable review, corroborated.)
- **Rejected:**
  - *Hardcoded genre→affordance checklist in the prompt* — maintenance trap + slot-filling + misbinding.
  - *Per-site affordance rules* — the maintenance burden the user refuses.

### D7 — Suggestion value is gated on **answer-completeness**, not quantity
- **Choice:** a link that answers *the asked question* elsewhere is **continuation / answer material** (mandatory, top billing) — per ADR-0009 a miss is an unfinished job. When the answer is complete here, speculative suggestions shrink toward zero. Replace the prompt's quantity gradient ("3 good, 5 great, up to 10") with a **justification gate**: emit a link only if you can state what question it answers that this page cannot; **zero is a good answer**; no target count. A hard cap stays **server-side** as a circuit breaker (a rail, never in the prompt).
- **Why:** the calling agent has its own agenda and doesn't need brainstormed questions; the continuation link is the single most valuable byte. "3 good, 5 great" is a value-gradient toward padding. (Fable.)
- **Rejected:**
  - *"Up to N" quantity target* — padding pressure.
  - *"One per real affordance found"* — "real affordance" is the undecidable relevance judgment again; would relocate the ambiguity.

### D8 — `ask_here` = **unreturned-content disclosure**, not curiosity
- **Choice:** every `ask_here` item must point at **specific content present on the page but not returned** (a coverage inventory), not a plausible-but-ungrounded question.
- **Why:** a follow-up question carries no information the calling LLM can't generate itself — *unless* it discloses on-page content that was omitted. That is its only defensible value. (Fable.)
- **Rejected:** *speculative follow-up questions* — pure padding for an LLM caller.

### D9 — Listings: item links + metadata ride the **records/answer**; affordances ride the digest
- **Choice:** on a listing, per-item `{name, rating, price, url}` are **records in the answer** (the existing `options`/record path), URLs rehydrated. Page affordances (next-page, filters, parent) go in the link digest. "Which is best" returns the **exhaustive option space with disclosed metadata** and at most a **criterion-disclosed lead** ("by rating, X leads — one lens"); never a crowned "best." Truncated listings owe a **next-page continuation link** + **"N of M" elision disclosure** (`item_total_seen`).
- **Why:** an item is one entity carrying data *and* a link — splitting them forces the caller to rejoin. Metadata is exactly what lets the caller apply *its* "best" criterion in one shot (ADR-0012 "best is criteria-less to a fetcher"; Exhaustive · Faithful · Neutral · One-shot). Coverage is genre-shaped by the D6 principle: a listing's primary entity is its items → many links; a product's is one product → few sub-resources.
- **Rejected:**
  - *Item URLs in the lean link digest* — bloats the digest and separates data from its link.
  - *Rich per-item metadata in the digest* — metadata belongs on records, not the affordance digest.

### D10 — Content includes **both** prose and JSON-LD (concatenate, don't replace)
- **Choice:** keep feeding the extractor prose **and** JSON-LD synth (already concatenated in `assemble_menu`); extend the same "concatenate, don't pick-one" to the **wire** `content_md` so the caller isn't blinded to prose when JSON-LD wins the display pick.
- **Why:** avoid invisibility; no runtime LLM dedup. The extractor already sees both; only the wire display currently replaces.
- **Rejected:** *replace prose with JSON-LD when longer/answer-bearing* (current wire behavior) — hides page content the caller may need.

### D11 — Flag **off-domain** `try_url` targets (injection guardrail) **[ADR-worthy]**
- **Choice:** off-domain rehydrated targets carry an explicit wire flag; off-domain suggestions require question-conditioned justification, not genre justification.
- **Why:** closed-set rehydration kills *hallucinated* URLs but **launders injected ones** — a page author's anchor labeled "full specifications" pointing anywhere gets a server-blessed `reason` handed to an autonomous agent. Anchor labels are attacker-controlled input. (Fable — the six-month miss.)
- **Rejected:** *treat all rehydrated links as equally trusted* — ignores that same-domain and off-domain carry very different trust.

### D13 — Ship v1 **shelf-free** (domain-side digest); hold the two shelf touches as deferred EVOLVEs

- **Choice:** build the entire v1 digest → `{{n}}` encoding → rehydration pipeline **in a2web domain code** from the already-flowing `_ExtractResult.links` (selectolax pass). **No shelf change on the critical path.** The two shelf-touching enhancements — (a) in-body links surviving as inline `[label](url)` markdown via `include_links=True`, (b) label-less `mailto:`/`tel:` retention (relax the `if href and anchor` gate) — are split out as separate shelf **EVOLVE** follow-ups, each via the `PROMOTE` workflow (own `../shelf-a2web` worktree, tag, CHANGELOG, ledger row).
- **Why (shelf-loop SEAM, generic-first then consumer-ranked):**
  - The digest/encoding/rehydration is a2web **product logic** (router-shape wire, `{{n}}` handles, closed-set), not generic substrate → **DUPLICATE/SKIP: build locally**, correct not to promote.
  - The reviews anchor is a labelled `<a href>` in a footer/tab → already captured by shelf `content_extract` v0.1.1's selectolax `a[href]` pass, already in `fc.links` (the response-side role filter at `fetcher.py:626` gates only the *caller-facing* `links`, never the digest source). So **the originating failure is fixed with zero shelf coupling.**
  - In-body inline markdown links = a real generic gap (**EVOLVE** `content-extract`→`convert-md`, `include_links` passthrough), but D1 already routes chrome links through selectolax; inline-markdown only adds *positional grounding*, which the design's own Open Question #1 already deferred. Not a blocker.
  - Label-less contacts = a legitimate **EVOLVE** on `content_extract` (passes resolution 0007 monotonicity: exposes more, removes nothing), but it is D4's separate feature, independent of the reviews fix.
- **Rejected:**
  - *Gate v1 on the shelf `include_links` contribution (original Task 1.1/1.3 framing)* — treated a deferred enhancement as a blocking dependency; forced a cross-package shelf evolution (content-extract → convert-md) onto the feature's critical path for grounding we already deferred. The fix ships without it.
  - *Hand-roll the `include_links` / gate-relax inside a2web* — banned by the Constitution + commit guard (no local fork of shelf code); the correct home is a shelf EVOLVE, done properly or not at all.

### D14 — Every surfaced URL must be **on-the-page**; memory/guessed URLs forbidden **[ADR-worthy]**

- **Choice:** any URL a2web emits — in `try_url` OR inline in the `answer` prose — must be traceable to the fetched page: either a `{{n}}` digest handle (an anchor href) or a URL that appears **literally in the page content**. A URL the model produces from its own training knowledge or by pattern-guessing (`…/reviews`, `…-yorumlari`) is forbidden. Enforced at the **prompt** (the `EXTRACT_ROUTER_V1` "LINKS IN THE ANSWER · HARD RULE" clause, v4) + the closed-set handle rehydration for `try_url`. When the needed link isn't on the page, the model says so (ADR-0009 honest absence) rather than inventing it.
- **Why:** a2web is a *grounded fetcher* — the caller trusts its URLs as page-derived, and has their own LLM for world-knowledge. An unverifiable memory-URL presented as grounded is a trust violation exactly when it's wrong, and it is the same class of harm as the originating guess bug — just laundered through answer prose. The eval (`findings_2026-07-11-answer-inline-links.md`) showed the model *already* writes raw answer URLs unprompted (pypi case), so `try_url`'s closed-set guarantee had a backdoor: the answer text. This rule closes it at the source.
- **Rejected:**
  - *Post-hoc strip any answer URL not in the closed digest set* — too blunt: the digest is built from `<a href>` anchors, so it would also strip **grounded page-text URLs** (visible plain-text URLs the model faithfully copied — the pypi case), throwing away good data. Risky ("might break something" — user). The prompt lever forbids the bad class at the source without endangering the good one.
  - *Encourage the model to supply useful links from its own knowledge* — it may be right (famous lib) but a2web cannot distinguish correct-from-memory from confabulated-from-memory; presenting an unverifiable URL as grounded breaks the retrieval contract.
  - *Provenance-flag every answer URL as "verified/unverified"* — considered; deferred. Adds wire surface; the prompt prohibition is the cheaper first move. Revisit if the model ignores the HARD RULE in practice (eval will tell).

### D12 — Instrument suggestion **uptake** before further generation polish
- **Choice:** log emitted `try_url` targets and correlate against subsequent `ask` calls (sqlite is already in the loop) to measure whether callers *follow* suggestions.
- **Why:** we're debating suggestion quality with zero data on whether any suggestion is ever used. Cheap to measure; will likely show continuation links get followed and speculative ones don't — turning taste into measurement. (Fable.)
- **Rejected:** *ship genre-aware generation without uptake telemetry* — flies blind for six months.

## Risks / Trade-offs

- **[Shelf coupling — retired for v1, see D13]** `include_links=True` and the label-less `mailto`/`tel` gate live in shelf-adopted `content_extract`, but neither is on the v1 critical path: the selectolax `links[]` already carries the chrome/reviews anchors into `fc.links`. The two shelf touches are deferred **EVOLVE** follow-ups (each its own `PROMOTE`-workflow change with a `../shelf-a2web` worktree + tag + ledger row), **never** a local fork.
- **[Prompt-injection laundering]** `try_url` can relay attacker-chosen URLs with a server-blessed reason. → D11 off-domain flag + question-conditioned justification; document that anchor labels are untrusted input.
- **[Token add on the common path]** the digest is net-new extractor input (~1.4k Haiku tokens on a product page). → cheap model, gated to `structural_form ∈ {product, listing}` so article fetches pay nothing; enforce a token budget as an eval gate (output tokens must be ≤ current baseline).
- **[Label→intent misbinding]** the new dominant error once fake URLs are impossible — model binds the wrong real link. → principle over table (D6), question-conditioned `reason` as a justification gate (D7), and the sentinel eval + `make bench` corpus catch regressions.
- **[Lossy link feed]** JS-rendered/lazy links may still be absent. → never assert genre-absence ("products usually have reviews; none here"); only question-scoped, evidence-scoped absence ("asked-for content not on this page; no link to it found in the extracted set") — asserting nonexistence on an imperfect feed would itself violate ADR-0009.
- **[trafilatura duplicate body]** `include_links=True` emitted the body twice in probe. → dedup step regardless.

## Migration Plan

1. **v1 (shelf-free, D13):** land the digest + `{{n}}` encoding + rehydration behind `structural_form ∈ {product, listing}` gating, sourced from the selectolax `fc.links` already in hand; article path unchanged. This fixes the originating reviews case with zero shelf change.
2. **Deferred shelf EVOLVEs (separate `PROMOTE`-workflow changes, not blockers):** (a) `content-extract`→`convert-md` `include_links` passthrough for in-body inline-markdown links; (b) relax the `if href and anchor` gate for label-less `mailto:`/`tel:` (D4). Each ships as its own `../shelf-a2web` worktree + namespaced tag + CHANGELOG + ledger row, adopted back via `RECEIVE` — folded in when they land, never gating v1.
3. Add the adversarial sentinel-collision eval to `make check` (offline, no live network) and re-run `make bench` for quality/cost parity before ship.
4. Add uptake instrumentation (D12) in the same change so telemetry accrues from day one.
- **Rollback:** the feature is additive and gated; disabling the digest assembly reverts to today's behavior with no wire break (the deferred consolidation is what would be breaking, and it's not in this change).

## Open Questions

1. **Caller-facing `content_md` placeholders** — does the wire `content_md` also carry `{{n}}` handles + a rehydration table, or keep real inline links? (Wire-shape change → "Ask First".) *Recommendation: keep real links on the wire; placeholders are an extractor-internal optimization.* **Update (2026-07-11): RESOLVED — keep out-of-band; inline placeholdering rejected.** After a mis-configured first probe (double-counted include_links on top of the full digest) and a corrected read (the D1 union is ≈ token-neutral), a Fable-council review settled it against inline: (1) **answer leak** — the extractor relays content faithfully, so an inline `[reviews]({{n}})` gets echoed into `answer` as caller-facing garbage; the out-of-band digest structurally cannot (handles live in the `try_url` field, not prose); (2) **`include_links` side effect** (verified milder than first claimed — near-additive on product pages, 0.98 text similarity; only restructures tables on complex articles) — residual cost is that `content_md` rides caller wires; secondary to the leak. So `content_md` keeps real inline links (not placeholders); the out-of-band digest stays the sole handle channel. If grounding is ever shown lacking by eval, the fallback is **digest context snippets** (selectolax parent-node text on the digest line), not inline. See `eval/findings_2026-07-11-include-links-flip.md` + task 7.1.
2. **Rehydrated links IN THE ANSWER (open hypothesis, defensively shipped).** The "answer leak" that argued against inline is neutralized by rehydrating the `answer` text (SHIPPED in `_phase_extract_answer`): a `{{n}}` the model writes into its prose becomes a real URL, not garbage — potentially a *feature* (a self-contained "reviews are at <url>" answer). This uses only the out-of-band digest, no `include_links`. Open question: for an AI caller, does an inline rehydrated link beat / duplicate the structured `try_url`? A/B eval-gated. See `eval/findings_2026-07-11-answer-inline-links.md`.
3. **`try_url` / `next_links` consolidation** — **BREAKING.** Collapse the two overlapping link-surfacing fields into one role-tagged field (`{url, reason, role, off_domain}`)? Deferred to its own change; both fields overlap in purpose and the merge breaks MCP parsers. *Recorded here so the redundancy is on the books.*
4. **Deployed custom model** — confirmed server default is DeepSeek V4 Flash; if it changes, re-run the sentinel eval against the new model (the matrix is cheap).
