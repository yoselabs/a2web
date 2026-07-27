## Context

The bench harness has four scoring axes and one sentinel for all of their failure
modes. `EvalRow` documents the ambiguity against itself, in adjacent comments:

```python
# Axis 3 — data-contract conformance (None = not applicable, e.g. WebFetch)
contract_conformant: bool | None = None
# Axis 4 — output clarity (None if not scored)
clarity_score: int | None = None
```

Same sentinel, two meanings, three lines apart. `next_links_score` inherits both and
adds a third: *the harness looked for a field that no longer exists.*

That third meaning is what actually happened. ADR-0015 folded `next_links` into
`other_pages` on the `AskResponse`, and `_next_links_block` still reads:

```python
envelope = fetch_result.metadata.get("envelope")
if isinstance(envelope, dict):
    block = envelope.get("next_links")      # never present on the query path
```

Verified against `eval/runs/2026-07-22_024912/trace/hn-front/a2web_extract/`, whose
stored envelope carries `['tier','confidence','answer','title','operator_hints',
'other_pages','refinement_axes']` — a populated `other_pages` TSV block, and no
`next_links`. `_score_next_links` then hits `if block is None: return`, and every
`a2web_extract` cell in the run recorded `next_links_score: None`.

The report handled it correctly *by its own rules* and still told us nothing: with
zero scored rows it renders `—`, the same glyph used for an axis that legitimately
does not apply to the corpus.

```
   what happened                       what the report showed
   ─────────────                       ──────────────────────
   ADR-0015 renames the field   ──▶    next_links │ —
   reader finds nothing                            ▲
   29 cells skip silently                          │
   axis is dead                        indistinguishable from
                                       "no listing URLs in this run"
```

## Goals / Non-Goals

**Goals**

- An axis that was asked for and produced nothing is loud, at the run level and in
  the artifacts.
- The candidate-block reader cannot be silently voided by an envelope rename again.
- Every rendered statistic states what it covers.
- A repeat measurement can be made genuinely independent, and a run says which it was.

**Non-Goals**

- Changing any production fetch, extraction, or envelope behaviour. The `query`
  envelope is correct; the harness is what is wrong.
- Changing `corpus.yaml`'s schema, its `needs` vocabulary, or adding an
  expected-failure declaration. Six cells in the last run scored quality 0 for
  *correctly* refusing per ADR-0009, which makes the aggregate uninterpretable — a
  real defect, but a corpus-vocabulary one that needs a validated schema to live in.
  Sequenced after the corpus change, deliberately not smuggled in here.
- Deciding what a case's lifecycle is, or whether the two corpora should converge.
- Making `make bench` part of `make check`. It stays live, quota-spending, and manual.

## Decisions

### D1 — Axis outcome is a typed record, not a nullable score

Replace the per-axis flat sentinel fields on `EvalRow` with one reusable
`dataclass(slots=True)` carrying score, disposition, and reason, instantiated once per
axis. Disposition is a closed enum: `SCORED` / `NOT_APPLICABLE` / `UNSCORED`.

*Alternative rejected:* keep the flat `*_score: int | None` fields and add parallel
`*_disposition` fields beside them. That is the redundancy the project forbids, and it
leaves the old sentinel readable by anyone who does not know to check its partner.
The flat fields are removed, not shadowed; `results.tsv` flattens at write time, which
is where flattening belongs.

*Consequence:* `_row_to_json`, `_RESULTS_FIELDS`, and the report's readers all change
together. That breadth is the point — a sentinel that means three things cannot be
narrowed one call site at a time.

### D2 — The candidate field is resolved from a literal per-system table

```python
_CANDIDATE_FIELD = {          # system name -> envelope field carrying the set
    "a2web_extract": "other_pages",   # ADR-0015 fold
    "a2web_detail":  "next_links",
}
```

*Alternative rejected:* try `other_pages`, fall back to `next_links`. Tolerant
lookup is inference, and inference is exactly how this broke — a fallback would have
silently absorbed the ADR-0015 rename and kept scoring the wrong thing on some systems
while scoring nothing on others, which is worse than the current failure because it
would have produced numbers.

This follows `wire._TSV_FIELDS`: the repo already decided that "which fields matter" is
a contract to be written down, not derived. A registered system missing from the table
is a build-time failure, not an unscored axis.

### D3 — A dead axis fails the run, but never discards it

A bench run costs live network, LLM quota, and ~8 minutes. Aborting on a broken axis
would destroy three good axes' worth of evidence to report a fourth. So: every
artifact is written first, then the run reports the broken axis by name in
`findings.md`, in the stdout summary, and via a non-zero exit.

*Alternative rejected:* report in `findings.md` only. `findings.md` is read by a human
who chose to read it — which is precisely the failure being fixed. The 2026-07-22 run
already recorded everything needed to see this, and it went unread for five days.

### D4 — Cache bypass by not constructing the cache

`Extractor` already accepts `cache: LlmCache | None`, and `LlmExtractorResource`
decides whether to build one (`llm_resource.py:248`). The bypass is a settings flag
that makes it build `None`.

*Alternative rejected:* `LlmCache(conn, ttl_s=0)`. Expiry-based bypass still *writes*,
so the first cell of a run poisons the rest, and a "bypassed" run would silently
become cache-served partway through. `None` reads nothing and writes nothing, which is
the only shape under which "N observations" means N.

### D5 — The offline guard reads the real model, not a copy of it

The four-axis tests in `tests/capabilities/output_benchmark/` run under `make check`
and must catch a rename without spending quota. The guard builds a real `AskResponse`
with a populated candidate set, serializes it through the production
`model_dump(mode="json")`, and asserts the reader finds the block.

This matters for provenance: the assertion's subject is the production model, so a
future rename breaks it. A hand-written fixture dict would have kept passing through
the ADR-0015 rename — a fake cannot witness a change to the thing it was copied from.
Paired with a vacuity floor asserting the constructed set is non-empty, per the
project's standing rule.

## Risks / Trade-offs

- **The re-run may expose more failures than it fixes.** Reviving the axis on 9
  `next_links_expected` cases will produce real scores for the first time, and they may
  be poor. That is the axis working. Any product defect it surfaces is recorded as a
  finding and sequenced, not fixed inside this change.
- **A non-zero exit on a broken axis could train people to ignore it**, the same way
  `tach`'s `[WARN]` for a missing module was ignored for weeks. Mitigated by D5: the
  offline guard is the primary gate and it fails in `make check`, before any run is
  spent. The exit code is the backstop, not the mechanism.
- **D1 touches every reader of `EvalRow` at once.** Contained: `llm_eval/` is 2,895
  lines with no importers outside itself and one architecture rule (packages may not
  import domain code) that this does not approach.

## Open Questions

- Should `not_applicable` be derived from the corpus entry (`next_links_expected`) or
  declared by the axis? Today it is derived, and the derivation is the same
  `next_links_expected` flag that is present on only 9 of 33 entries — meaning 24
  entries are `not_applicable` by omission rather than by statement. Resolving this
  properly belongs to the corpus-schema change; this change records the disposition
  faithfully from whatever the corpus currently says.
- The stdout summary already carries a live per-cell renderer (`live_sink.LiveSink`).
  Whether the broken-axis banner belongs there or only in the final summary is a
  presentation call to settle during implementation.
