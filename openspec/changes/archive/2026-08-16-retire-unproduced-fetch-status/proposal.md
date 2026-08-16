## Why

`FetchStatus` declares three members — `ok`, `failed`, `partial` (`models.py:68-71`).
A census of `src/` finds **no producer of `partial`**: every assignment in
`fetcher_response.py` writes `ok` or `failed`, and no other module constructs the
field. It is a declared-but-unreachable value on a live wire contract.

That is a contract that lies. A calling agent reading the tool schema sees a state
it can never receive, and any consumer that branches on it holds dead code it has
no way to discover is dead.

The system has already decided against it in prose without acting on the code.
ADR-0019, accepted 2026-08-08, traces the failure envelope field by field and
writes `status` as **`(ok | failed)`** — *"a coarse, lossy collapse of
`final_verdict` down to one bit."* One bit is two members. The same ADR shows why
a third member has nothing left to carry: `retrieval_incomplete` already holds the
partial-retrieval axis and is documented there as **orthogonal to `status`, not
derived from it**, and `Verdict` (15 members) and `TerminalOutcome` (7) carry the
detail.

Filed as `a2web-0br` out of the `flag-interaction-gated-sections` follow-up list,
with the instruction: *"Do not leave it declared and unreachable."*

## What Changes

- **Remove `FetchStatus.partial`.** The enum becomes `(ok, failed)`, matching what
  the code has always emitted and what ADR-0019 already declares.
- **Add an architecture guard that makes the recurrence impossible to miss**
  (`tests/architecture/test_every_fetch_status_has_a_producer.py`). It walks `src/`
  for `FetchStatus.<member>` producer sites and asserts every declared member has
  at least one. A future member added to the enum without a producer fails the
  suite rather than shipping onto the wire silently. Follows the existing census
  idiom — `test_every_hint_code_has_a_factory.py`, including its
  not-vacuous self-check.
- **Update the `app-composition` requirement** that spells the enum out as
  `(ok, failed, partial)`, and give it a scenario for the producer rule.

## Impact

| Surface | Effect |
|---|---|
| `src/a2web/models.py` | one line removed |
| `tests/architecture/` | one new guard file |
| `openspec/specs/app-composition/spec.md` | one requirement modified (via the delta) |
| CLI contract (`tests/contracts/cli/`) | **none** — `partial` appears nowhere in the captured contracts |
| Wire goldens (`tests/contracts/wire/`) | **none** — verified: the string `partial` is absent from `list_tools.json` and every call/error golden; the tool schema does not inline the status enum |
| Emitted responses | **none** — no response has ever carried `partial` |

The narrowing is safe in the direction that matters: removing a value **no
producer ever emitted** cannot break a consumer, because no consumer can ever have
received it. The reverse narrowing — dropping a value in use — is the dangerous one
and is not what this is.

## Non-goals

- **Not giving `partial` a producer.** Considered and rejected in `design.md`: the
  state it would name is already carried by `retrieval_incomplete`, and inventing a
  producer would put one fact on two axes that can then disagree.
- **Not promoting `TerminalOutcome` to the wire.** ADR-0019 suggests that as the
  path *if* the single caller-situation enum argument ever wins. It has not won,
  no bead asks for it, and reserving a slot for a design nobody has committed to is
  what produced this defect in the first place.
- **Not touching `Verdict`, `Confidence`, or `CacheState`.** Each is produced; only
  `FetchStatus` had an unreachable member. The new guard covers `FetchStatus`
  only — generalising the census across every wire enum is a larger change with its
  own argument to make.
