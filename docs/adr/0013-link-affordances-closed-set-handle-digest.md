# ADR-0013 — Link affordances: feed the extractor real links via closed-set `{{n}}` handles

**Status:** **Accepted** (decided 2026-07-11)
**Date:** 2026-07-11
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0005 (multi-source extraction input — the "menu" this extends), ADR-0009 (never silently miss a URL — a missed sub-resource is a miss), ADR-0014 (grounded-URL tenet — the trust half of this feature), openspec change `surface-page-links-to-extractor` (full decision + rejection record: D1, D2, D3, D6)

## Context

The originating failure: on a Hepsiburada product page an agent asked "summarize the reviews." Reviews live on a **separate** URL (`…-yorumlari`). a2web correctly returned honest incompleteness (ADR-0009), but its `try_url` drilldown was a **wrong guess** — a SKU-variant URL lifted from JSON-LD `offers.url` — because the real reviews link was never shown to the extractor.

Probe-verified root cause was **structural blindness, not fabrication**: `trafilatura.extract(...)` strips all hrefs; even `include_links=True` removes the reviews tab as element-level boilerplate before links matter. The reviews href survives **only** in the separate selectolax `links[]` pass, which was never fed to the extractor. `try_url`'s "must appear verbatim in content" rule was therefore impossible to satisfy and unenforced — so the model guessed.

Constraints that shaped the fix: no per-site rules or URL-scheme guessing (a maintenance trap the owner refuses); token cost must not increase output tokens vs. baseline; quality is non-negotiable.

## Decision

Let the extractor **see the page's real links** and hand one back safely, generically, with zero per-site rules. Three coupled mechanism decisions (the fourth, generation posture, is D6 below):

**D1 — Two link sources, unioned.** In-body links (via `trafilatura include_links=True`, kept with surrounding prose for positional grounding) **∪** the selectolax `links[]` chrome pass (nav/footer/tab) **minus** the in-body set. In-body links carry reasoning context; the reviews *tab* is chrome and lives only in selectolax. The union loses nothing. *(v1 ships shelf-free from the selectolax `fc.links` already in hand; the `include_links` in-body half is a deferred shelf EVOLVE — see the openspec change D13. It is additive.)*

**D2 — Encode links as `{{n}}` handles; server rehydrates closed-set.** Each surviving link → `{{n}}` (numeric, delimited) + anchor label + trimmed path (domain shown only if off-domain). The extractor emits **handles**; the server maps handle → real href via a closed-set table; unknown handles are dropped, never guessed. This buys input trim (the URL is the expensive part), output trim (`{{3}}` not a 100-char URL), and — decisively — **correctness**: a model cannot hallucinate a URL it never types, and a handle absent from the table is rejected. The URL is replaced on **output**, not input, so full URL signal is preserved for the model's judgment.

**D3 — Safe deterministic cuts only; the LLM does all relevance judgment.** Drop only provably-same-document or unfetchable links (self-link, `#fragment`-only, normalization dup, `javascript:`, exact-dup href). Everything else is fed. Relevance ("is this the reviews page?") cannot be judged deterministically across marketplaces without per-site rules; the cheap `{{n}}` encoding dissolves the need to filter (~200 links ≈ ~1.4k input tokens on a product page).

## Key rejections (re-litigation guard — full record in the openspec change)

- **Bare `L1`/`L2` handles** — closed-set rehydration on bare `L1` **eval-demonstrably corrupted** "Xiaomi **L1** Desk Lamp." Delimited `{{n}}` is collision-clean. (D2)
- **Anchor-label-only (drop the URL)** — probe-quantified quality loss: ~40% of a real page's anchors had non-unique labels where only the URL disambiguates; page-*type* often lives only in the URL. (D2)
- **Relevance filtering to ~15 "good" links** / **role-based dropping (nav/footer)** — smuggles undecidable relevance into a deterministic filter; the mega-menu is tagged `primary`, and footer-dropping kills `mailto:`/`tel:` contacts. (D3)
- **Deterministically inlining chrome links into prose** — impossible: trafilatura already deleted the element, so there is no anchor position to reattach to. (D1)

## D6 — Affordance suggestions are genre-aware via a **principle**, not a maintained table

The prompt carries the principle *"surface links that extend the page's primary entity — deeper detail · community signal · transaction terms · sibling/parent entities,"* with 1–2 explicitly non-exhaustive examples. Per-genre expectations ("product pages have reviews") live in the **eval corpus** as tests, not the prompt.

**Why:** the failure was never that the model lacks world knowledge that products have reviews — it never saw the link (D1 fixes that). A principle generalizes to genres never enumerated. A hardcoded genre→affordance table is a maintenance trap and creates **slot-filling pressure**: it binds the closest-looking link to each expected slot, and closed-set validation stops *fake* URLs, not *wrong real* ones — so label→intent misbinding becomes the dominant error. **Rejected:** hardcoded genre checklist in the prompt; per-site affordance rules.

## Consequences

- New extractor input (the `{{n}}` digest) on the tail, byte-stable cache prefix preserved; gated to `structural_form ∈ {product, listing}` (approximated pre-LLM by presence of `json_synth`/`record_synth` candidates) so the article path pays nothing.
- `try_url` entries are populated from **rehydrated hrefs only**; a handle absent from the table drops the entry and emits `llm_wobble` without failing the fetch.
- Label→intent misbinding is the new dominant error class (fake URLs are now impossible) — guarded by D6 (principle over table) + question-conditioned `reason` justification + the sentinel eval + `make bench` corpus.

## Re-evaluation triggers

- If the deployed extractor model changes from DeepSeek V4 Flash, re-run the adversarial sentinel-collision eval (the matrix is cheap).
- If eval shows flat anchor labels failing to ground the model, add **digest context snippets** (selectolax parent-node text per line) — out-of-band, never inline placeholders (see the openspec change Open Question #1).
- If the `include_links` in-body EVOLVE lands, union it in via set-difference on normalized hrefs and dedup trafilatura's duplicate body block — additive, no wire change.
