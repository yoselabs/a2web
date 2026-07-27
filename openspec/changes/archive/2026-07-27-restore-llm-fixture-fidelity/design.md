# Design

## The pattern this generalizes

Four instruments have now reported success while measuring nothing:

| instrument | the lie | how it was caught |
|---|---|---|
| 30/32 architecture tests | passed against an empty source tree | noticed by accident; fixed with `_walk.walked_files(minimum=…)` |
| `test_tools_return_pydantic_not_str` | matched `@a2kit.read`, a decorator that no longer existed | noticed during the a2kit sunset |
| `_StubProvider` | `del system, user` — prompt-blind | caught by rendering the routing path deliberately |
| `tests/eval_replay/harness.py:165` | rebuilds `ExtractionResult` with no `routing=` | caught while looking for field data on the previous item |

Each was caught by accident, by someone looking for something else. The existing
rules in CLAUDE.md — *"never add a structural guard without an assertion that it
found something"* and *"never treat a golden as proof of correctness"* — cover
walks and golden sets. Nothing covers **test doubles**, which is the category
that has now failed twice in one week and cost a design decision.

## D1 — Fidelity is a property of the double, checked centrally

Two rejected alternatives:

**Per-double tests** (what `test_stub_provider_fidelity.py` is). Rejected: it is
the redundancy the constraint forbids, and it does not generalize — a new double
added tomorrow gets no check unless someone remembers to write one. That is the
same "someone remembers" that failed four times.

**A shared base class doubles must inherit.** Rejected: inheritance is opt-in.
A double that forgets to inherit is invisible, which is the failure mode.

**Chosen: a discovery walk over test modules**, finding classes that structurally
quack like an LLM provider/extractor double, and asserting each is either
contract-faithful or declares its degraded arm. Discovery is opt-out rather than
opt-in, so a new blind double fails by default.

Declaration mechanism: a class attribute naming the arm, e.g.
`DOUBLES_ARM = "unparsable"`. Machine-checkable, greppable, and it puts the
intent next to the code rather than in a registry that can drift.

**Risk — this check is itself a structural guard, so it can go vacuous the same
way.** It carries a floor (`minimum=`) and a bidirectional sensitivity case: a
double hard-wired to always emit JSON must FAIL, not pass. Without that second
case the check would accept a fixture that is blind in the opposite direction,
which is precisely the mistake made when first fixing `_StubProvider` — the
initial patch used `"structural_form" in system` where `system` is a *tuple* of
prompt-cache blocks, so the membership test silently never matched.

## D2 — The cassette format: extend and fail loud, never default

`capture.py` writes `artifacts.llm` — `answer`, tokens, cost, latency, model,
template name. Post-parse only. The routing payload is not merely absent from
the recorded files; the format cannot express it.

So this is not a "populate a missing field" fix. Two pieces:

1. **Capture side** records the routing payload.
2. **Replay side** fails loud on a cassette that cannot express it.

The failure must be loud specifically because the alternative — default to
`None` — is bit-for-bit the current defect. A compatibility fallback here would
re-create the bug under the name of politeness, and per the no-backcompat
constraint, legacy cassettes get re-captured rather than tolerated.

The format must also distinguish **"recorded as lost"** from **"format cannot
say"**. Without that a deliberately-degraded case is indistinguishable from a
stale one, and the loud failure becomes un-silenceable for legitimate cases.

## D3 — Re-capture cost

Five corpus cases hold captured LLM responses. Re-capture is live network plus
LLM quota, subscription provider only (ADR-0016). Bounded and one-time.

Cases that cannot be re-captured (dead URLs, changed pages) SHALL fail loud and
be re-pointed or retired deliberately. Silently keeping a stale cassette is what
this change exists to stop.

## D4 — Sequencing

This change MUST land before `fix-extraction-signal-fidelity`. That change moves
wire goldens deliberately. Blessing goldens while 16 replay cases still run the
degraded branch would freeze the lie a second time — the exact failure CLAUDE.md
already records for `list_tools.json`, where a `~95%` typo survived seventeen
rounds of wire review because the golden proved only that nothing had *changed*.

## What this change does not do

No production code path is touched. If any production change turns out to be
required to make a double faithful, that is a finding to report — not something
to fix quietly here, because a product change smuggled inside a test-fidelity
change is unreviewable.
