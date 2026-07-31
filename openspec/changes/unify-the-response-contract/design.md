## Context

Three files, one concept, 17 shared commits and rising. The measurement is in
`docs/findings/2026-07-31-structural-scan.md`; the six defect instances were each
verified by reading the code.

The important framing: this is **not** a tidying job. Five of the six instances
are live behaviour — a relabelled link kind, a dropped anchor, a dropped
handler candidate set, a field that means two things by tool, and an ADR-0009
floor recovered by string-matching English. The structure is why they keep
happening; the instances are why it is worth fixing now rather than after
`decompose-fetcher-into-files`.

## Goals / Non-Goals

**Goals**

- A decision made once is carried, not reconstructed.
- The hint vocabulary and the severity ladder each exist in exactly one place.
- The response contract is a module you can point at.
- `fetcher_response.py`'s external reads of `FetchContext` are absorbed, so
  `context.py` can later be sliced.

**Non-Goals**

- Decomposing `fetcher.py`. Different change, and must not run concurrently.
- Merging the two-phase `confidence` decision. It is deliberate and documented;
  only the naming is wrong.
- Changing what any invariant *means*. Every ADR stays as written.

## Decisions

### D1 — Carry the typed value; delete the reconstruction

`TerminalOutcome` is already a closed 7-value vocabulary computed from
observations. The fix is not clever: put it on the response path and delete
`fetcher_response.py:435,442,449`.

The reason this is worth stating as a decision rather than doing silently is the
history. `actions/terminal.py:8-16` documents that the *previous* design keyed on
a projection instead of the observations, and was changed for that reason. The
projection-keying came back one file downstream. Carrying the value is the thing
that makes it not come back a third time.

### D2 — The hint code set becomes a declared enum, and string-matching goes away

Four sites match hint codes by string. Seven codes exist only as inline literals
with no factory. Both facts are symptoms of the same absence: there is no
declaration of what the codes are.

Declare it. Then the string matches become enum comparisons, and a typo in a code
is a build error rather than a silently-never-matching branch.

This is also the cheapest guard in the change: once the set is declared, a test
that every constructed hint carries a declared code is trivial and non-vacuous.

### D3 — The severity ladder is stated once, and the docstrings cite it

Nine docstrings currently encode `critical` = wall, `warning` = unverified,
`info` = verified-dead. None of them is the source; the reader assembles the
ladder by reading all nine.

State it once, in the module that owns the response contract. This is what makes
`severity == "warning"` at `fetcher_response.py:442` obviously wrong rather than
plausible — today it reads as a reasonable check because the ladder is folklore.

### D4 — The `kind` fold: fix the vocabulary, not the label

Two ways to stop `kind="structural"` lying:

1. Add `structural` to `NextLinkKind` so the fold's claim can be true.
2. Carry each handler's assigned kind through the fold.

**Take (2).** No handler ever produces a structural-shaped link — the value would
be added to a vocabulary nothing populates, purely so a fold can keep
overwriting. `models.py:456` defines `structural` as "deterministic continuation
— pagination, page-order"; a Reddit post drilldown is not that, and no relabelling
makes it so.

`NextLink.anchor` is dropped on the same line. Carry it. It is the label ADR-0014
reasoning depends on (anchor labels are attacker-controlled, which is a reason to
carry them *and* treat them as untrusted — not a reason to discard them).

This is the breaking part of the change, and it is a correction: consumers
currently receive a kind that is false for the common case.

### D5 — Where the module boundary goes

`fetcher_response.py` is already 740 lines and already the projection layer. The
temptation is to make it the new module by renaming it. Resist: it is 740 lines
because it accreted, and this change removes several hundred (the six
re-derivations) while adding the catalogue moved out of `models.py`.

The shape that follows from the census:

```
response/
├── vocabulary.py     hint codes (closed enum) + the severity ladder, once
├── hints.py          the 9 factories + the 7 codes that lack one
├── project.py        FetchContext/FetchResponse → the envelope
└── wire_fields.py    the ONE TSV field table
```

`models.py` keeps types. `wire.py` keeps encoding. Import direction stays as it
is today (`models.py:29` imports from `.wire`; `wire.py` does not import
`models`) — the new module may import both.

### D6 — The TSV table: one owner, and a guard that the halves agree

The anti-seam is real and must be respected. `_next_links_tsv` and
`_other_pages_tsv` pick their column set by inspecting *typed* rows (`lk.kind`,
`p.off_domain`) — they need model instances **before** `model_dump`, and
`wire.encode_envelope` runs after it. The pre-dump column decision is genuinely
model-side.

So the split is not "move everything to `wire.py`". It is: **one declared table
naming which fields are TSV**, consumed by both halves, with a guard asserting
the model-side branches and the wire-side table describe the same set. The
introspection ban survives — the table stays literal — and the duplication that
defeated it does not.

`headings` is encoded by nobody today (`_is_tsv_shaped` rejects the
`[level, text]` pair shape). Decide explicitly whether it is TSV or not and put
the answer in the table, rather than leaving it as a gap between two
implementations.

Also: `models.py:18` imports `lean_wire.encode_tsv` directly rather than through
`wire.py`, so the codec has two in-tree consumers. One.

### D7 — Sequencing against the decomposition

This change **must land before** `decompose-fetcher-into-files` phase two, and
**must not overlap** phase one.

- Phase one (the tree + the loop) does not need this change.
- Phase two slices `context.py` per node, and 41 of `FetchContext`'s 69 fields
  are read externally by `fetcher_response.py`. Those reads have to become a
  contract before the context can be split along it.

Attempting them together turns a decomposition into a rewrite — the explicit
lesson from v0.23.

## Risks / Trade-offs

- **This is a breaking envelope change** (`kind` values, `anchor` presence) and
  therefore gated by Ask First. It is also a *correction*: consumers today get a
  kind that is wrong for the common case. Say that in the changelog rather than
  presenting it as a neutral refactor.
- **~1350 existing assertions read `structured_content`.** Behaviour is meant to
  be unchanged everywhere except the two wire corrections. Any other test that
  moves is a finding, not a fixture to update — and per `fb:tests-not-requirements`,
  it means the change did something unintended.
- **Moving 228 lines of agent-facing English risks changing it.** It is
  ADR-0009 copy that has been tuned; move it verbatim and diff the strings.
- **The module split could be one file too many.** Four files for a concept
  currently spread over three is only a win if each has one purpose. If
  `vocabulary.py` and `hints.py` cannot be told apart in practice, merge them —
  the criterion is one purpose per file, not maximum files.

## Open Questions

- Does the response module live at `src/a2web/response/` or absorb
  `fetcher_response.py` in place? Leaning a directory, because the census says
  four purposes.
- Is `headings` TSV? Nothing encodes it today and nothing appears to want it.
  Recording "not TSV" in the table is a legitimate answer; leaving it undecided
  is not.
- Should `retrieval_incomplete`'s two phases be two fields, or one field with a
  documented finalization point? Two fields is honest but widens the envelope.
  Needs a call.
- `_compose_next_links`' drop is wrong when `request_next_links` is False — but
  is it *also* wrong when True? The stated justification ("the LLM re-ranked
  handler candidates") is sound in that case. Verify before deciding whether the
  fix is conditional or total.
