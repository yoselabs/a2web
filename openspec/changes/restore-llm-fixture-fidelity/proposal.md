# Test doubles must prove they satisfy the contract they double

## Why

a2web has now shipped, in one session, **four** structural guards that reported
success while measuring nothing. Two were found this week and two are on record
in CLAUDE.md:

| instrument | how it lied |
|---|---|
| `_StubProvider` | `del system, user` — returned prose whatever contract it was handed, so every wire golden and most `query` tests silently ran the routing-LOST branch |
| `tests/eval_replay/harness.py:165` | rebuilds `ExtractionResult(...)` with no `routing=`, so all 16 replayed eval cases run the degraded branch; the cassette format cannot even express routing |
| 30 of 32 architecture tests | passed against an empty source tree (fixed by `_walk.walked_files(minimum=…)`) |
| `test_tools_return_pydantic_not_str` | stayed green for a whole migration while matching `@a2kit.read`, a decorator that no longer existed |

The cost is not hypothetical. The `_StubProvider` lie is the direct cause of a
real design decision being made wrong: the ADR-0015 index-loss signal was
measured as *"fires on every query — permanent noise"* and shelved to
`BACKLOG.md` as blocked on a discriminator that never needed to exist. The
measurement was of the fixture. Live spikes against a real provider later
recovered the payload 15/15.

The replay harness is worse than the stub in two ways: it stubs `extract()`
rather than the provider, so the `_StubProvider` fix does not reach it; and
`capture.py` writes only post-parse fields (`answer`, tokens, cost, latency,
model, template), so the frozen cassettes are **structurally incapable** of
recording the routing payload. All five captured LLM responses in the corpus are
prose with `template_name: extract_router_v1` — the routing path ran, and what
it produced was never saved.

CLAUDE.md already carries the rule this violates — *"Never add a structural
guard without an assertion that it found something"* — and a companion —
*"Never treat a golden as proof of correctness."* A golden captured through a
lying fixture freezes the lie. What is missing is any mechanism that applies
those rules to **test doubles**, as opposed to walks and golden sets.

`tests/capabilities/ask_response/test_stub_provider_fidelity.py` (landed in
`e8e5dbc`) is a point fix for exactly one double. Under the no-redundancy rule
it should not sit beside a general mechanism; it should be subsumed by one.

## What Changes

- **A contract-fidelity check over every LLM test double in the repo.** Each
  double must either satisfy `EXTRACT_ROUTER_V1`'s contract, or explicitly
  declare which degraded arm it exists to double. Undeclared blindness fails.
  Carries a non-vacuity floor, per the repo's own doctrine — a check that finds
  zero doubles must fail, not pass.
- **Subsume and delete `test_stub_provider_fidelity.py`.**
- **Fix `tests/eval_replay/harness.py`** to carry the routing payload.
- **Extend the cassette format** to record it, and **fail loud** on a cassette
  that cannot express routing rather than silently defaulting to `None`. No
  backward-compatible fallback: a silent default is precisely the failure mode
  under repair.
- **Re-capture** the affected corpus cases so the eval corpus stops running the
  degraded branch.

## Impact

- Affected specs: `test-fidelity`
- Affected code: `tests/eval_replay/harness.py`, `eval/_capture/capture.py`,
  `tests/capabilities/ask_response/*`, `tests/architecture/`
- **Wire**: none. This change touches no production code path.
- **Risk**: re-capture requires live network and LLM quota (subscription
  provider only, ADR-0016). Cassettes that cannot be re-captured will fail loud
  rather than silently degrade — intentional, and the point of the change.
- **Sequencing**: this should land BEFORE any behaviour change gated on routing
  outcomes. Otherwise the eval corpus gets blessed around a lie for the second
  time.
