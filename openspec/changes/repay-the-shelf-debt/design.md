## Context

Evidence: `docs/findings/2026-07-31-primitives-scan.md`. The scan's own summary
is worth keeping in view — **adopt gaps are thin, and that is a good result.**
17 packages consumed, every pin current, `anyembed` / `duckdb-sidecar` /
`git-porcelain` / `managed-region` genuine non-gaps.

What the scan found is not under-adoption. It is three narrower failures:

1. a2web fixed a shared primitive locally and did not repay it,
2. a2web adopted a primitive and hand-rolled the same job alongside it,
3. a2web routed *around* a broken shared package instead of fixing it.

(3) is the one worth naming, because it looked like good judgement at the time
and produced the worst outcome in the list.

## Goals / Non-Goals

**Goals**

- The three encoder fixes exist in the shared package, and `a2kay` stops running
  the bugs.
- Each of the five paid-for gaps is either closed upstream or recorded as a
  standing exception with a reason.
- Where a primitive is adopted, it is used.
- The error taxonomy distinguishes "your key is missing" from "we crashed".

**Non-Goals**

- Adopting `page-tsv` in a2web. Possibly a follow-on, and explicitly not the
  goal — the goal is that the shared copy is correct.
- The large T7 structural entries. Separate changes.
- Promoting hedged-race-first-wins. One call site.

## Decisions

### D1 — Routing around a broken shared package is half a decision

`2026-07-26-sunset-a2kit-dependency/design.md:99-104` rejected `page-tsv`:
"Adopting re-imports the problem". Correct for a2web, and it left a sibling repo
running three known defects for months.

The rule this change encodes: **rejecting a shared package for a defect obliges
you to file the defect.** a2web had more than the report — it had the fix,
written and tested, in `wire.py:124-175`. The cost of the omission is borne by
`a2kay`, which never saw the analysis.

This is also why `substrate-adoption` is worth a capability rather than a task
list: the failure is procedural and will recur.

### D2 — Notify `a2kay`, do not silently fix

`a2kay` consumes `page-tsv` and its output shape will change when the guards
land — a previously-resurrected field will stop appearing, a previously-blanked
field will start carrying content. Those are corrections, and they are still
changes to a live wire.

Fix the package, tell the consumer, let the consumer take the bump. Do not treat
"it was a bug" as license to change a sibling's output without notice.

### D3 — Promotion order follows blast radius, not effort

1. **`page-tsv`** — the only one with a live cross-repo consumer.
2. **`record-mine`'s `[role=heading]`** — the shipped behaviour contradicts
   a2web's own normative spec, so today either the code or the spec is lying to
   a reader.
3. **`content-extract`'s knobs** — retires two funnel exemptions, a direct
   `trafilatura` dep, and restores links + headings to two handlers.
4. **`dom-schema`'s ROT-under-universal-container** — closes a rot-detection hole
   that currently costs a live network probe.
5. **`json-in-html` normalization** — largest, and it wants
   `lift-the-item-set-and-renderer` to have moved the renderer first.
6. **`any-browser` CDP-connect** — a container-environment bug; a2web already has
   `correlated_witness` making it observable, which is the mitigation holding.

### D4 — The error taxonomy is the highest-value item that is not a shelf change

`except AppError` at `error_wire.py:97` is dead because a2web raises no
`AppError` subclass. Every failure — a missing LLM key, an unavailable resource,
a null-deref — becomes `UnexpectedDefect` kind `"bug"` and renders as
`"Internal error (UnexpectedDefect): …"`.

That is a product defect, not a tidiness one: an operator whose key is
unconfigured is told a2web has a bug.

Making `ResourceUnavailable` (`state.py:186`), `LLMNotAvailable`
(`packages/llm_extract/errors.py:6`) and `JudgeParseError` (`judge.py:63`)
`AppError`s with proper kinds activates four unreachable `_KIND_LABELS` entries
immediately. Small change, disproportionate effect.

Note this interacts with `close-wire-level-adr-0009-leaks`, which covers the dead
branch from the wire-leak side. Coordinate: one change makes the branch
reachable, the other asserts what reaches it.

### D5 — Use-what-is-adopted is cheap, and the drift is the argument

Each of these is a few lines. The reason to do them is not the lines:

- **Three omit-empty predicates in one file** (`models.py:786` inline,
  `models.py:678` via `PruneEmpty`, and the unused `prune_dict`) means the
  question "is this field empty?" has three answers that nothing compares.
- **`fmt_dur` vs `live_sink.py:176`** already disagree for every duration ≥ 7s.
  That is not a hypothetical drift; it has happened.
- **`results.tsv` via `csv.DictWriter`** reproduces exactly the QUOTE_MINIMAL
  behaviour `pyproject.toml:50-56` cites as the reason lean-wire exists.

Adopting a primitive and hand-rolling beside it is worse than not adopting: the
reader sees the import and assumes one implementation.

### D6 — jina through `http_fetch` is a correctness change, not a cleanup

`tiers/jina.py` building its own client means jina has **no circuit breaker** and
hand-mapped verdicts outside the `FetchVerdict` closed enum. Those are the two
things the tier contract is for.

`zyte`/`firecrawl` are a genuine gap — POSTs to JSON APIs, and `http_fetch` is
GET-only. Either widen `http_fetch` or record the exception; do not leave it
implicit. And extend `handlers/README.md:17`'s hand-rolled-client ban to
`tiers/`, since `tiers/` is where it is being violated.

### D7 — Promote a2web's own substrate while the ledger is open

`lazy.py` (43 lines) + `scope.py` (109) — `Lazy[T]`, LIFO `ResourceScope`,
`memoized` — and `cli.py:field_to_typer_annotation`. Both written *after* the
2026-07-27 sweep, so neither appears in its verdict table; they are not
deliberate omissions, they are unscanned.

Apply the normal bar (DEEP · STABLE · WINS) rather than promoting because they
are noticed. `scope.py` in particular is load-bearing for a2web's cold-start
guarantee and a promotion must not loosen it.

## Risks / Trade-offs

- **Six shelf changes is a lot of cross-repo work**, each with its own promotion
  loop. This change is the ledger and the reference implementations; it will not
  land in one sitting. Sequence by D3 and let items close individually.
- **Fixing `page-tsv` changes `a2kay`'s output.** Corrections, but real. D2 is
  the mitigation and it depends on actually notifying.
- **Removing the `trafilatura` direct dep** is blocked on `content-extract`
  shipping the knobs. Do not retire the funnel exemptions early — the exemptions
  are honest today and would become false.
- **The taxonomy change alters error prose on the wire.** `"Internal error
  (UnexpectedDefect)"` becomes a specific kind for several real cases. Better,
  and a change to what callers parse.

## Open Questions

- After the guards land in `page-tsv`, can a2web's `wire.py` consume it? The
  original rejection was about the defects; with them fixed, the remaining
  question is whether a2web's literal `_TSV_FIELDS` policy fits the package's
  shape. Re-evaluate, do not assume either way.
- Does `http_fetch` widen to POST, or do `zyte`/`firecrawl` stay exempt? Widening
  a GET-only primitive to carry a JSON POST may be the wrong shape for it.
- Is `scope.py` promotable without loosening the cold-start guarantee that
  `test_cold_start_laziness.py` pins? If the shelf version needs a more general
  contract, keep it local.
- `a2effect.lint` — a declared-error-closure checker, unused, in a repo that
  records losing `a2kit lint rego` as a real loss. Is it the Rego replacement, or
  a different thing wearing a similar name? Worth ten minutes before the
  re-homing entry is actioned.
