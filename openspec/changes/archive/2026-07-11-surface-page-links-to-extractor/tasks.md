## 1. Shelf touches — DEFERRED follow-ups, NOT blockers (see design D13)

> **Resolved by the shelf loop (SEAM):** shelf `content_extract` v0.1.1 already runs the selectolax `a[href]` pass, and those links already flow into a2web via `fetcher.py:251` → `fc.links` (the response-side role filter at `fetcher.py:626` gates only the caller-facing `links`, never the digest source). So **v1 ships entirely shelf-free** from `fc.links`. The two items below are separate `PROMOTE`-workflow changes; do them only after v1, each in its own `../shelf-a2web` worktree with a namespaced tag + CHANGELOG + ledger row, adopted back via `RECEIVE`.

- [x] 1.1 *(EVOLVE — SHIPPED)* `content-extract`→`convert-md` `include_links=` passthrough so in-body anchors survive as inline `[label](url)` markdown (positional grounding — Open Question #1). Shipped as `convert-md-v0.8.0` + `content-extract-v0.2.0` (shelf `main`, ledger 0044/0045). Adopted back in a2web (ledger 0046/0047). a2web-side flip pending bench — see 7.1.
- [x] 1.2 *(EVOLVE — SHIPPED + LIVE)* relaxed the shelf selectolax gate (`if href and anchor`) to retain label-less `mailto:`/`tel:` with an href-derived label (D4). In `content-extract-v0.2.0`; **live in a2web now** (contacts flow into `fc.links` → digest, zero a2web code change).
- [x] 1.3 v1 sources the digest from the selectolax `fc.links` already in hand — **no shelf dependency** (verified against installed `content_extract` v0.1.1).

## 2. Link digest assembly (link-affordances)

- [x] 2.1 Add a digest builder over the selectolax `fc.links` already in hand (v1) — `link_digest.build_digest`. When the deferred in-body-markdown EVOLVE (1.1) lands, union in-body links via set-difference on normalized hrefs and de-dup the trafilatura duplicate-body block — additive, no v1 dependency.
- [x] 2.2 Implement safe deterministic cuts only: self-link, `#fragment`-only, trailing-slash/normalization dup, `javascript:`, exact-dup href. No relevance filtering.
- [x] 2.3 Retain `mailto:`/`tel:` regardless of role; surface raw value. *(Label-less contacts need the deferred shelf gate-relax 1.2; labelled ones flow today.)*
- [x] 2.4 Dedup by target URL with union of distinct anchor labels.
- [x] 2.5 Gate digest assembly on a pre-LLM product/listing proxy (`structural_form` is post-hoc — approximate with presence of `json_synth`/`record_synth` candidates); article path pays nothing. (`fetcher._build_link_digest`, cap `_DIGEST_LINK_CAP=200`.)

## 3. Placeholder encoding + rehydration

- [x] 3.1 Encode each link as `{{n}}` (numeric, delimited) + label + trimmed path; show domain only when off-domain. Build the closed-set handle→href table. (`LinkDigest.render` / `.table`)
- [x] 3.2 Implement closed-set rehydration matching only exact `{{n}}` (never bare substrings); drop unknown handles. (`rehydrate_handle` / `rehydrate_text`)
- [x] 3.3 Add the adversarial sentinel-collision unit test (product names "Xiaomi L1", "WH-L7", SKU) asserting no in-name corruption and unknown-handle drop. (Offline, in `make check` — `tests/capabilities/link_affordances/test_link_digest.py`, 11 tests.)

## 4. Extractor wiring (extraction)

- [x] 4.1 Append the digest to the extractor input menu on the tail (preserve byte-stable cache prefix). (`extractor._link_digest_suffix`, rides `parts.tail`.)
- [x] 4.2 Replace the router prompt's quantity gradient with a justification gate ("emit only if you can state the question it answers; zero is valid"); add the "extend the primary entity" principle + 1–2 non-exhaustive examples; remove any genre checklist. (`EXTRACT_ROUTER_V1` v3.)
- [x] 4.3 Instruct handle-by-`{{n}}` emission; never raw URL. (Prompt + parser accept `{handle, reason}`.)
- [x] 4.4 Parse + validate emitted handles closed-set in the router payload; rehydrate at the domain seam; emit `llm_wobble` on violation without failing the fetch. (`fetcher._rehydrate_routing_handles`.)
- [x] 4.5 Constrain `ask_here` items to disclose specific unreturned page content — coverage-inventory framing ("content that IS on this page but did NOT make it into your answer"). (`EXTRACT_ROUTER_V1` v3.)

## 5. Response wiring (ask-response)

- [x] 5.1 Populate `try_url` from rehydrated hrefs only; drop entries whose handle is absent. (`_project_routing` filters empty-url entries.)
- [x] 5.2 Add an off-domain flag to `try_url` entries on the wire. (`NextUrl.off_domain` + omit-when-False serializer.)
- [x] 5.3 Promote the continuation link to top priority when the answer is incomplete (ties into retrieval-completeness). *(Prompt: "put that continuation link FIRST".)*
- [x] 5.4 Emit question-scoped, evidence-scoped absence when the answer and its link are both not found; never assert genre-level nonexistence. Added an "EVIDENCE-SCOPED ABSENCE" clause to the `answer` prompt guidance (`EXTRACT_ROUTER_V1`): scope absence to THIS page/evidence ("not stated on this page", "no such link among the page's links"), never assert it does not exist at all — a genre-level nonexistence claim is a false negative when the content lives on an unfetched page (ADR-0009). Cache-prefix byte-stability preserved (tail-only).

## 6. Listing records (link-affordances / record-extraction)

- [x] 6.1 Ensure listing item links + metadata (rating/price) ride the records/answer path with rehydrated URLs, not the lean digest. *(Already satisfied by design: `ListingOption` carries `url: str | None` — the item's real DOM href from `record_mine` extraction — plus `detail` (price/rating). Per-item links ride the `options` record path; the lean digest carries only page-level affordances (next-page/filters/parent). Verified against `models.py::ListingOption`.)*
- [x] 6.2 "Which is best" returns the exhaustive option space + disclosed metadata + at most a criterion-disclosed lead; never a crowned "best". *(Already satisfied: the SELECTION-neutrality clause is live in the `answer` prompt guidance (no own "best"; criterion-disclosed lead as ONE lens; relay source-stated preference attributed) + `refinement_axes` (judgable criteria) + the rank-don't-skip `options` shelf — the shipped `answer-neutrality-for-selection` / ADR-0012 work.)*
- [x] 6.3 Truncated listings emit a next-page continuation link + "N of M" elision disclosure (`item_total_seen`). *(Already satisfied: the `listing_partial` / `items_loaded`+`items_total` / `item_total_seen` machinery exists (`_phase_listing_completeness`, `_apply_llm_listing_oracle`, `listing_partial_hint`); the next-page continuation link now rides `try_url` via the digest handle path with the "continuation FIRST" prompt clause.)*

## 7. Content shape (content-expectations)

- [x] 7.1 *(resolved — inline REJECTED; keep v1 out-of-band; context-snippets is the fallback)* Evaluated in-body-link grounding. Fable-council review killed the inline-placeholder / `include_links` path on two counts cost-analysis missed: (1) **answer leak** — the extractor relays content faithfully, so an inline `[reviews]({{n}})` gets echoed into `answer` free-text as caller-facing garbage; v1's out-of-band digest has no such mode; (2) **`include_links` side effect** — verified milder than first claimed: on product-like pages it is near-additive (0.98 text similarity, whitespace-only diffs), only restructuring tables on complex articles; residual cost is that `content_md` rides the `fetch_raw`/`ask(include_content)` wires. Secondary to the leak, which is decisive alone. Verdict: keep the v1 out-of-band digest. If eval later shows flat labels failing, add **digest context snippets** (~80 chars of selectolax parent-node text per line, gated to vague labels) — out-of-band, ~30 lines, ~80% of the grounding at ~10% of surface. Gated on an LLM bench of the `affordance` corpus cases. Findings: `eval/findings_2026-07-11-include-links-flip.md`.
- [x] 7.2 Concatenate prose + JSON-LD for the caller-facing `content_md` (stop replacing prose when JSON-LD wins the display pick). Pure a2web domain — no shelf dependency. Implements design **D10**. Surgical, guarded reversal of the 2026-06-07 pick-one decision (user-approved "implement with a guard"): `_wire_content_md` intercepts ONLY the json_synth-wins branch — when above-floor prose coexists with a JSON-LD render that would otherwise replace it, surface BOTH (subset-suppressed via the extractor-menu dedup). Guards: (a) threaded/longer RECORD sets keep their legacy replace semantics (they render structure prose lost — untouched); (b) Article/NewsArticle JSON-LD (`ContentCandidate.is_prose_metadata`, set from the LD `@type` in `_escalate_via_json`) is a metadata echo — it never displaces real above-floor prose (returns prose, no concat) — closing the historical blog.html regression. Extractor menu untouched (`assemble_menu` still sees every candidate). Tests: `tests/capabilities/extraction/test_wire_content_md.py` (5); the `test_threaded_discussion_replaces_regardless_of_length` contract still holds.

## 8. Guardrails + telemetry

- [x] 8.1 Document that anchor labels are untrusted input; require question-conditioned justification for off-domain suggestions. Documented in **ADR-0014** (anchor labels are attacker-controlled; off-domain targets flagged + question-conditioned justification) and operationalized in the router prompt: added an OFF-DOMAIN clause to the `try_url` guidance — the anchor label is untrusted, emit an off-domain handle ONLY when the question itself needs the external resource, justified from the question, never the label's claim (the digest already renders the domain for off-domain links, so the model can act on it).
- [x] 8.2 Add uptake instrumentation: log emitted `try_url` targets to sqlite and correlate against subsequent `ask` calls to measure follow-through. Shipped as `src/a2web/uptake.py` (free functions `record_suggestions` / `note_visit` over the shared sqlite connection, idempotent `a2web_url_suggestions` table, no AppState/wire change). Hooked best-effort in `fetch()` on the ask path (`_record_uptake`): `note_visit(requested_url)` closes prior suggestions + emits `try_url_followed`; `record_suggestions` logs this ask's rehydrated targets + emits `try_url_suggested`. Correlation is slash/fragment-insensitive. Tests: `tests/capabilities/uptake/test_uptake.py` (6, offline).

## 9. Evaluation + gates

- [~] 9.1 Re-run the adversarial sentinel eval against the deployed model (DeepSeek V4 Flash) if it changes. **Bench-deferred → BACKLOG.md** (2026-07-11 section) — `make bench` is live-network/quota, not in `make check`.
- [~] 9.2 Add a token-budget assertion: extractor output tokens must be ≤ current baseline; digest input within budget. **Bench-deferred → BACKLOG.md** (2026-07-11 section).
- [x] 9.3 Encode per-genre affordance expectations as `eval/corpus.yaml` cases — new `affordance` class: hepsiburada-product-reviews, amazon-product-reviews-elsewhere, trendyol-listing-which-best (ADR-0012 no-crown), github-repo-issues-affordance, contact-page-channels. Standing "never lose a case" rule added to the corpus header + CLAUDE.md. *(`make bench` is live-network/quota — run before ship, not here.)*

## 10. ADR promotion + docs

- [x] 10.1 Promote the [ADR-worthy] decisions to top-level a2web ADRs; cross-reference this change. Shipped as **ADR-0013** (link-affordance mechanism — D1 two-source, D2 `{{n}}` handle rehydration, D3 safe-cuts-only, D6 principle-not-table) + **ADR-0014** (grounded-URL product tenet — D14 on-the-page-only, D11 off-domain flag). INDEX updated (also backfilled the missing ADR-0012 row).
- [x] 10.2 Update CLAUDE.md / envelope docs for the rehydrated + off-domain-flagged `try_url` semantics. Added a "Never surface a URL that isn't on the page" line to the CLAUDE.md "Never" section (ADR-0014 tenet: on-the-page-only, `NextUrl.off_domain` flag, closed-set rehydration, the `.format()` quad-brace hazard).
