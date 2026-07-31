## Why

**a2web's product invariants are documented as one concept and implemented as
three files.** `fetcher.py`, `fetcher_response.py` and `models.py` co-change in
**17 commits** — 3× the next-largest triple — and the coupling is *strengthening*,
not decaying:

| pair | era A (05-09..06-15) | era B (06-16..07-31) | last 30d |
|---|---|---|---|
| `fetcher ↔ fetcher_response` | 5 (0.17/0.71) | **21 (0.53/0.84)** | 20 (0.56/0.83) |
| `fetcher ↔ models` | 9 (0.30/0.75) | **19 (0.47/0.86)** | 18 (0.50/0.90) |
| `fetcher_response ↔ models` | 4 (0.57/0.33) | **18 (0.72/0.82)** | 17 (0.71/0.85) |

Cross-confirmed by two independent methods (git co-change; AST responsibility
census). It is not a migration artifact — every commit subject is a product
feature, and the list reads as a single concept:

```
v0.14 envelope deviation trim · v0.21 router-shape envelope · ADR-0005 candidate
menu · v0.25 never-tolerate-any-unfetched-URL · honest partial-listing signal ·
structural "more exists" fallback · ADR-0015 withheld-body index · tier
truthfulness + classify_terminal + honest 404s · thin-not-wall · empty-vs-wall
discrimination · promote corroborated complete small pages to ok
```

Every ADR-0009/0012/0014/0015 tenet lands as an edit to all three files.
`packages/llm_extract/router_payload.py` extends the cluster to four.

**The cost is not aesthetic. It is six live instances of the same defect shape:**
a decision made upstream in a typed closed vocabulary, erased at a boundary, then
reconstructed downstream from a string.

1. **The ADR-0009 floor is derived from the severity of an English sentence.**
   `actions/terminal.py` defines `TerminalOutcome`, a closed 7-value
   classification. `fetcher.py:2009` computes it, `:2010-2024` maps it to a hint
   code and **throws the value away** — it is on neither `FetchContext` nor
   `FetchResponse`. Then `fetcher_response.py:435,442,449` reconstructs the same
   classification by string-matching the hints it just produced. The sharpest
   symptom is `severity == "warning"`: it reads back the severity that
   `content_not_found_hint(verified=False)` chose, **in order to recover the
   `verified` boolean that was passed in** — a round-trip through a message
   catalogue to recover a boolean. `fetcher_response.py:427` calls the hint *"the
   SINGLE source of truth for incompleteness"*, while `actions/terminal.py:8-16`
   exists precisely because the previous design keyed on a projection instead of
   the observations.

2. **`kind="structural"` at `fetcher_response.py:294` discards every handler's
   own classification.** Handlers set `drilldown`, `related`, `discussion` —
   **none ever sets a structural-shaped one**, and `NextLinkKind` has no
   `structural` member. The fold relabels every entry to the one value its source
   vocabulary cannot express, and `models.py:456` defines `structural` as
   "deterministic continuation — pagination, page-order", a false claim for a
   Reddit post drilldown. The same line silently drops `NextLink.anchor`. The
   authors know: `models.py:729-734` notes the `kind` column is dropped from the
   TSV "when every row is `drilldown` (the common handler-derived case)" — in the
   same file where the fold calls them structural.

3. **`empty_confirmed` is decided once and re-derived anyway.** Set at
   `fetcher.py:1946` from `actions.empty.is_confirmed_empty`, read correctly at
   `fetcher_response.py:375`, then **re-derived at `:685`** from
   `any(h.code == "content_empty" ...)` — shadowing the imported name of the real
   predicate. Its sibling `small_page_confirmed` is carried across properly. Two
   adjacent promotions, two different mechanisms.

4. **`_compose_next_links` (`:274-281`) drops `fc.next_links_handler` wholesale**
   when the LLM list is non-empty, justified by "the LLM re-ranked handler
   candidates" — but `fetcher.py:2462` only passes them when `request_next_links`.
   When it is False, the LLM never saw them and they are dropped anyway.

5. **`retrieval_incomplete` and `confidence` are each decided twice**, so neither
   is final for `query` callers while both are final for `fetch_raw` callers.
   **The same field name means two different things depending on which tool you
   called.** (The confidence half is deliberate and documented at `:638-646` — a
   genuine two-phase decision. The fix there is naming the phases, not merging
   the sites.)

6. **Two TSV field tables, three owners, one contract.** `wire._TSV_FIELDS` is
   literal *on purpose* — CLAUDE.md: "inference is how a field added to
   `AskResponse` silently changes the agent-facing wire". But `models.py` holds a
   second implicit table in its serializer branches (`other_pages` at `:921`,
   `links` at `:665`, `next_links` at `:667`), which `wire.py` defers to via its
   already-TSV guard, while `operator_hints` / `refinement_axes` / `options` /
   `content_candidates` are encoded in `wire.encode_envelope`, and `headings` by
   **nobody**. Nothing asserts the two tables describe the same set. The rule is
   honoured against *introspection* and defeated by *duplication* — the exact
   failure it names.

Two structural findings underneath all six:

- **`models.py` is 25% prose and 12% wire projection.** 228 lines
  (`:141-368`) are an operator-hint message catalogue containing **no types** —
  agent-facing English encoding the ADR-0009 severity policy. **The severity
  ladder (`critical` = wall, `warning` = unverified, `info` = verified-dead) is
  discoverable only by reading nine docstrings scattered through a
  type-definition file. There is no place where it is stated once.** That is
  precisely what makes it re-derivable by string-match.

- **Hint construction is spread across 5 modules.** 9 factories in `models.py`,
  plus raw `OperatorHint(...)` at 10 further sites. Seven codes exist only as
  inline literals with no factory. The set of codes is a de-facto closed enum
  that is **nowhere declared** — while four sites match on it by string.

- **`fetcher_response.py` is 740 lines CLAUDE.md never mentions.**

Why now, and why before `decompose-fetcher-into-files` phase two: **41 of
`FetchContext`'s 69 fields are read externally by `fetcher_response.py`.** Until
the response contract absorbs those reads, `context.py` cannot be sliced
per-node. This change is the blocker on that one.

## What Changes

- **Name the concept and give it a module.** The retrieval-completeness /
  response contract — what its own commits call it — becomes the owner of the
  hint vocabulary, the severity ladder, the terminal classification, and the
  wire field tables.
- **Carry `TerminalOutcome` through instead of re-deriving it.** It becomes a
  field on the response path; `fetcher_response.py:435,442,449`'s string-matching
  is deleted. `verified` is a boolean the whole way, never a severity round-trip.
- **Declare the operator-hint code set as a closed vocabulary**, with the seven
  inline-literal codes given factories, and the four string-match sites reading
  the enum.
- **State the severity ladder once.** One place says `critical` = wall,
  `warning` = unverified, `info` = verified-dead — and the nine docstrings cite
  it rather than restating it.
- **Stop the `kind="structural"` relabel.** Carry each handler's own
  classification, and carry `NextLink.anchor` instead of dropping it. Either
  `structural` becomes expressible in the source vocabulary or the fold stops
  claiming it.
- **One `empty_confirmed`.** Delete the `:685` re-derivation; the field set at
  `fetcher.py:1946` is the answer, as it already is for `small_page_confirmed`.
- **Fix `_compose_next_links`' unconditional drop**, which discards handler
  candidates the LLM was never shown.
- **Name the two phases of `retrieval_incomplete` and `confidence`** so a field
  name does not mean two things by tool.
- **One TSV field table, asserted.** Whichever module owns it, a guard asserts
  the model-side and wire-side sets are the same — the introspection ban is
  preserved, the duplication hole is closed.
- **Move the hint message catalogue out of `models.py`.**

## Capabilities

### New Capabilities

None. This is one concept becoming one implementation; the capabilities already
exist and are stated across `retrieval-completeness`, `fetch-response`,
`ask-response`, and `link-affordances`.

### Modified Capabilities

- `retrieval-completeness`: the terminal classification SHALL be carried, not
  reconstructed from a rendered message; the severity ladder SHALL be declared
  once.
- `fetch-response`: the operator-hint code set SHALL be a declared closed
  vocabulary; a field decided once SHALL NOT be re-derived downstream; the wire
  field table SHALL have one owner and an equality guard.
- `link-affordances`: a link's kind SHALL be the kind its producer assigned.

## Impact

- `src/a2web/fetcher_response.py` — the six erase-and-re-derive sites
- `src/a2web/models.py` — hint catalogue and wire projection move out
- `src/a2web/fetcher.py` — `TerminalOutcome` carried rather than discarded
- `src/a2web/wire.py` — one field table, with a guard
- `src/a2web/packages/llm_extract/router_payload.py` — the fourth fragment
- `tests/` — ~1350 field-presence assertions read `structured_content`; the
  behaviour is meant to be unchanged, and where it changes (kind, anchor) it is
  a wire change
- **Breaking:** `other_pages[].kind` values change for handler-derived rows, and
  `NextLink.anchor` starts appearing. Both are envelope-shape changes and need
  the Ask First gate.

## Out of Scope

- Slicing `FetchContext` per-node. That is
  `decompose-fetcher-into-files` phase two, which this change unblocks.
- Decomposing `fetcher.py`'s pipeline. Separate change, and deliberately not
  simultaneous: v0.23 already demonstrated the failure mode of a refactor that is
  also a bug fix.
- The `confidence` two-phase decision itself, which is deliberate. Only its
  naming is in scope.
