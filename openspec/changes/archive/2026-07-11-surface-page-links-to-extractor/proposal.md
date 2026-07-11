## Why

When an agent asks a marketplace **product** page to "summarize the reviews," the reviews often live on a **separate URL** (e.g. Hepsiburada's `…-yorumlari`). a2web correctly reports "no reviews on this page" — but **cannot hand back the reviews-page URL**, so the caller is stranded. Root cause is not fabrication; it is **structural blindness**: the server-side extractor is fed only trafilatura prose / JSON-LD, both of which **strip anchor hrefs**, so the model never sees the reviews link and *guesses* one (and guesses wrong — observed in a real trace). The reviews link exists as a real anchor in the DOM the whole time. This change lets the extractor **see the page's real links** and hand back the right one — generically, with no per-site rules — turning a dead-end miss into a loud, correct continuation.

## What Changes

- **Feed the page's real links to the extractor.** Two sources, unioned: `trafilatura(include_links=True)` for **in-body** links (kept in place, with surrounding text for positional grounding) + the existing selectolax anchor pass for **out-of-body** chrome links (nav/footer/tab — where the reviews *tab* lives) via set-difference.
- **Encode links as collision-proof placeholder handles.** Each surviving link becomes a `{{n}}` numeric sentinel + its anchor label + a trimmed path (domain shown only if off-domain). The extractor emits **handles, not URLs**; the server **rehydrates** handles to real hrefs via a closed-set lookup. This kills URL hallucination (a handle not in the table is dropped) and slashes output tokens. Eval-proven collision-safe on Haiku 4.5, gemini-2.5-flash, and DeepSeek V4 Flash (the server default).
- **Safe deterministic cuts only** — self-link, `#fragment`-only, trailing-slash dup, `javascript:`, exact-dup href. **No relevance filtering** (can't be done deterministically across marketplaces) — the LLM does all relevance judgment. `mailto:`/`tel:` are **retained** (their href IS the payload, and trafilatura destroys them).
- **Genre-aware suggestions, dynamically.** The extractor already classifies `structural_form`; it already knows (world knowledge) that products afford reviews/specs/warranty. The prompt carries a **principle** ("surface links that extend the page's primary entity"), *not* a maintained genre→affordance table. Per-genre expectations live in the **eval corpus**, not the prompt.
- **Continuation vs. speculation.** A link that answers *the asked question* elsewhere is **answer material** (promoted, top billing) — not a nice-to-have suggestion. Suggestion budget is gated on **answer-completeness**, not a quantity target.
- **Listings:** item links + metadata (rating/price) ride the **records/answer**, not the link digest; page affordances (next-page, filters) go in the digest. "Which is best" presents the option space with disclosed metadata and at most a **criterion-disclosed lead** — never a manufactured "best."
- **Content includes both** trafilatura prose **and** JSON-LD (concatenate, don't replace) so nothing the model needs goes invisible.
- **Guardrail:** `try_url` rehydration can *launder* attacker-controlled anchor labels into agent-facing suggestions — **off-domain** targets are flagged on the wire.
- Two decisions are **deferred, not made** (recorded in design.md): (1) whether caller-facing `content_md` also carries placeholders + a rehydration table; (2) **BREAKING** consolidation of `try_url` and `next_links` into one role-tagged field.

## Capabilities

### New Capabilities
- `link-affordances`: the link digest (two-source union, safe-cuts, dedup-by-target with label union), `{{n}}` placeholder encoding + closed-set rehydration, the affordance/continuation semantics (principle-driven, neutral, completeness-gated), and the off-domain injection flag.

### Modified Capabilities
- `extraction`: the extractor input menu now includes the placeholder link digest; the router prompt gains the affordance **principle** (not a genre table) and instructs handle-by-`{{n}}` emission; the router payload parses/validates emitted handles against the closed set.
- `ask-response`: `try_url` entries are rehydrated real hrefs (never model-typed URLs); continuation links are promoted when the answer is incomplete; off-domain targets carry an explicit flag.
- `content-expectations`: page content is built with `include_links=True` and **concatenates** trafilatura prose with JSON-LD synth rather than replacing one with the other.

## Impact

- **Code:** `src/a2web/fetcher.py` (assemble the digest into the extractor menu; rehydration seam), `src/a2web/fetcher_response.py` (`_project_routing`, `build_ask_response` — rehydrate, off-domain flag), `src/a2web/packages/llm_extract/{extractor.py,prompts.py,router_payload.py,wobble/}` (digest in prompt, handle emission + closed-set validation), `src/a2web/packages/content_extract` (shelf-adopted — `include_links=True` needs a config passthrough or shelf contribution; the label-less `mailto`/`tel` gate is a known drop-gap), `src/a2web/domain.py`/`models.py` (encoding + rehydration helpers, wire fields).
- **Dependencies:** no new top-level deps. Touches shelf-adopted `content_extract` (constraint noted).
- **Contracts:** `ask` envelope gains rehydrated/flagged `try_url` semantics (additive; the breaking consolidation is deferred). `make bench` is the pre-ship gate; a new adversarial sentinel-collision eval is added.
- **Product invariants:** advances ADR-0009 (a miss becomes a loud continuation) and ADR-0012 (affordances = categories of what exists, never rankings).
