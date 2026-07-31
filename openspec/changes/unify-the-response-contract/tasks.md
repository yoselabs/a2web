# Tasks

Blocks `decompose-fetcher-into-files` phase two. Must **not** run concurrently
with phase one — v0.23 demonstrated what a refactor that is also a bug fix costs.

Gate first: the `kind` and `anchor` corrections are envelope-shape changes, and
CLAUDE.md's Ask First list covers them.

## 1. Confirm the shape before moving anything

- [ ] 1.1 Confirm the Ask First gate for the breaking envelope change:
      `other_pages[].kind` values change for handler-derived rows, and
      `NextLink.anchor` starts appearing.
- [ ] 1.2 Verify `_compose_next_links`' drop (`fetcher_response.py:274-281`) —
      it is clearly wrong when `request_next_links` is False (the LLM never saw
      them). Determine whether it is also wrong when True before choosing a
      conditional or total fix.
- [ ] 1.3 Decide the module location (design Open Questions): `src/a2web/response/`
      vs absorbing `fetcher_response.py` in place.
- [ ] 1.4 Decide whether `headings` is TSV. Nothing encodes it today; "not TSV"
      is a legitimate answer, "undecided" is not.

## 2. The vocabulary and the ladder

- [ ] 2.1 Declare the operator-hint code set as a closed vocabulary.
- [ ] 2.2 Give the seven factory-less codes (`answer_truncated`,
      `content_guidance`, `retrieval_incomplete`, `index_lost`,
      `captcha_redirect`, `browser_unavailable`, …) factories.
- [ ] 2.3 Convert the ten raw `OperatorHint(...)` sites — `fetcher_response.py:345,
      600, 617, 668`, `fetcher.py:831, 1899, 2497`, `tiers/browser.py:129, 198`,
      `handlers/reddit.py:730` — to factories.
- [ ] 2.4 Convert the four string-matching dispatch sites to enum comparison.
- [ ] 2.5 Add the guard: every constructed hint carries a declared code.
- [ ] 2.6 State the severity ladder once (`critical` = wall, `warning` =
      unverified, `info` = verified-dead). Have the nine docstrings cite it.
- [ ] 2.7 Move the 228-line hint catalogue (`models.py:141-368`) out. **Move the
      strings verbatim and diff them** — this is tuned ADR-0009 copy.

## 3. Carry the terminal classification

- [ ] 3.1 Put `TerminalOutcome` on the response path — today `fetcher.py:2009`
      computes it and `:2010-2024` discards it.
- [ ] 3.2 Delete the three reconstruction sites at `fetcher_response.py:435, 442,
      449`.
- [ ] 3.3 Delete `fetcher_response.py:427`'s claim that the hint is "the SINGLE
      source of truth for incompleteness".
- [ ] 3.4 Verify: editing a hint's message text must not change any
      classification.

## 4. Stop the re-derivations

- [ ] 4.1 Delete the `empty_confirmed` re-derivation at `fetcher_response.py:685`
      (which shadows the imported name of the real predicate). Read the field set
      at `fetcher.py:1946`, as `small_page_confirmed` already does.
- [ ] 4.2 Apply the `_compose_next_links` fix decided in 1.2.
- [ ] 4.3 Name the two phases of `retrieval_incomplete`. The confidence
      two-phase decision is deliberate (`:638-646`) — name its phases, do not
      merge the sites.
- [ ] 4.4 Confirm no field name means two different things depending on which
      tool the caller invoked.

## 5. The link-kind correction

- [ ] 5.1 Carry each handler's assigned kind through the fold at
      `fetcher_response.py:294`, instead of relabelling to `structural`.
- [ ] 5.2 Carry `NextLink.anchor` instead of dropping it on the same line.
- [ ] 5.3 Reconcile `models.py:729-734` — the note about dropping the `kind`
      column "when every row is `drilldown` (the common handler-derived case)" —
      with the fold that was calling them all structural.
- [ ] 5.4 Update the CHANGELOG to present this as a **correction**, not a neutral
      refactor: consumers today receive a kind that is false for the common case.

## 6. One TSV table

- [ ] 6.1 Declare the TSV field set literally, once. Keep it literal — the
      introspection ban stands.
- [ ] 6.2 Have both halves consume it: `models.py`'s serializer branches
      (`other_pages:921`, `links:665`, `next_links:667`) and
      `wire.encode_envelope` (`operator_hints`, `refinement_axes`, `options`,
      `content_candidates`).
- [ ] 6.3 Preserve the anti-seam: `_next_links_tsv` (`:733`) and
      `_other_pages_tsv` (`:746`) choose columns from *typed* rows, before
      `model_dump`. The pre-dump column decision stays model-side; only the
      declaration is unified.
- [ ] 6.4 Add the equality guard: model-side and wire-side sets describe the same
      fields.
- [ ] 6.5 Route `models.py:18`'s direct `lean_wire.encode_tsv` import through
      `wire.py`. One in-tree consumer.

## 7. Absorb the context reads

- [ ] 7.1 Inventory the 41 `FetchContext` fields read externally by
      `fetcher_response.py` (of 69 total).
- [ ] 7.2 Turn those reads into the response contract's interface, so
      `context.py` can later be sliced per node.
- [ ] 7.3 Confirm `decompose-fetcher-into-files` phase two is unblocked, and say
      so in that change's design.

## 8. Close out

- [ ] 8.1 `make check` green. Any test that moves beyond the two intended wire
      corrections is a finding — investigate it, do not update the fixture
      (`fb:tests-not-requirements`).
- [ ] 8.2 `make bench` — this change touches the response envelope, which is one
      of the stated triggers.
- [ ] 8.3 Add corpus cases for the corrected `kind` and the restored `anchor`
      before the context is lost.
- [ ] 8.4 Update CLAUDE.md: `fetcher_response.py` is currently 740 lines it never
      mentions.
- [ ] 8.5 Move the T2 entries to `BACKLOG-CLOSED.md`.
