## Why

The `ask` response has grown a family of "here's more content" fields — `ask_here`, `try_url`, `next_links`, `options`, `refinement_axes`, `headings` — that were added independently and never reconciled. Two structural problems, plus a naming/grammar cleanup:

1. **No governing principle.** The `ask`/`query` tool deliberately withholds the body for token economy (`include_content=False` by default). That withholding creates a blindness: the caller — itself an AI agent that never sees the body — knows only the answer to *one* question and is blind to everything else the page holds. `ask_here` already exists to close that gap (its prompt contract is literally *"a coverage inventory of what you left on the table"*), but this is an *ungoverned* behavior — no ADR, no tie to the withheld-body mechanism, no rule keeping it orthogonal to its siblings. This change writes that principle down as **ADR-0015 (the withheld-body index)** and makes the field family fall out of it.

2. **Two parallel "other-page" families.** `next_links` (handler/LLM-sourced, TSV, capped 10) and `try_url` (LLM question-conditioned, `{{n}}`-handle rehydrated) both mean "go to another URL," with nothing reconciling them. They merge into one `other_pages` field with a per-item `kind` (`structural` | `drilldown`).

3. **Rename + terse grammar.** `ask` → `query`, `question` → `query`; `ask_here` → `also_here` (the index of THIS page's un-surfaced content; `refine` was rejected — it collides with `refinement_axes`). `also_here` entries adopt a terse *query grammar* (a deletion rule, not a DSL) so each entry is a concrete index pointer, not a hedged question.

The cost lever is not the strings' own tokens — it is fetch hit-rate. `also_here` points at content one **cache-served re-ask** away (no new proxy fetch); `other_pages` each cost a **new proxy fetch**. Making that certainty/cost asymmetry legible lets the caller spend on the scarce resource (the fetch) correctly.

## What Changes

- **Author ADR-0015 "the withheld-body index"** (product tenet, sibling to 0009/0012/0014) — see `design.md`. Complements ADR-0012 (answer stays exhaustive over the *asked* set; the index covers only the *un-asked* remainder — it must never force a same-page re-fetch of data that was asked for).
- **Rename the tool `ask` → `query`, param `question` → `query`** (`canonical_name_override` moves to `query`). `fetch_raw` / `refresh` unaffected.
- **Rename `ask_here` → `also_here`** — the index of same-page content the answer did not surface. Entries adopt the terse query grammar (target + operator; `,` list · `vs` contrast · `/` alternatives · CAPS the decider; `?` only for DECIDE; split `and` compounds).
- **Merge `next_links` + `try_url` → `other_pages`**: `list[OtherPage]` = `{url, reason, kind: "structural"|"drilldown", off_domain}`. `kind=drilldown` iff the link's selection depends on the question; else `structural`. **ADR-0014 is preserved in full** — `{{n}}` closed-set rehydration, `off_domain` flag, and question-conditioned `reason` for drilldowns all carry over.
- **Non-overlap rules** (governed by ADR-0015): `also_here` indexes prose/product/discussion remainder and is dense there; on a `listing` it defers to `options` + `refinement_axes` and stays sparse. `also_here` never restates a `heading`, an `option` row, or a `refinement_axis`.
- **Cost-asymmetry legibility**: expressed in ADR-0015 + the tool description (`also_here` = cheap cached re-ask; `other_pages` = new fetch) — NOT as new wire fields (cheap default).
- **Validate via spikes** (A: terseness vs fidelity; B: CAPS; C: lean vs fat description) — on the subscription/cheap provider from `bench-cost-isolation`, never metered API.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `ask-response`: tool `ask`→`query`, param `question`→`query`; `ask_here`→`also_here` (index framing + query-grammar contents); `next_links` + `try_url` merged into `other_pages` with a `kind` discriminator; `also_here` non-overlap rules; cost-asymmetry documented.
- `extraction`: `EXTRACT_ROUTER_V1` emits `also_here` in query grammar and a unified `other_pages` shape (kind-tagged), preserving ADR-0014 handle grounding.
- `link-discovery`: unchanged — `FetchResponse.next_links` (the `fetch_raw` page envelope) stays; the ask-side fold into `other_pages` is specced under `ask-response`.

## Impact

- **BREAKING (MCP + parsers):** `ask`→`query`, `question`→`query`, `ask_here`→`also_here`, `next_links`+`try_url`→`other_pages`. Breaks installed MCP clients, `~/.claude.json`, `canonical_name_override` pins, envelope parsers. **Applies LAST** — after `unify-escalation-executor` lands — as one deliberate version bump + `make install-global`.
- `src/a2web/models.py` — `AskResponse` field renames; new `OtherPage` model; retire `NextUrl`/`NextLink` (or fold); serializer/`_prune_wire` wiring. **Plus** the `ADR-0009` docstring at `models.py:226` that references `ask_here`.
- `src/a2web/fetcher_response.py` — `_project_routing` (`also_here`), `_compose_next_links` → `_compose_other_pages` (merge + `kind`), preserve `{{n}}` rehydration + `off_domain`.
- `src/a2web/packages/llm_extract/prompts.py` — `EXTRACT_ROUTER_V1` follow-up + links instructions.
- `docs/adr/0015-*.md` + `docs/adr/INDEX.md` + `CLAUDE.md` "Never" line — promote ADR-0015 on apply.
- `CLAUDE.md:38,40,81` — update `ask(url, question)` / `ask_here` / affordance-class references.
- Tests: `tests/contracts/*.json`, `tests/capabilities/ask_response/`, `tests/capabilities/*` referencing `ask`/`ask_here`/`next_links`/`try_url`.
- Validation is spike-driven (see `design.md`), NEVER a full `make bench` on metered API.
