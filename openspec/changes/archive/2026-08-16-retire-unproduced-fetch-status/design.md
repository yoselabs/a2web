# Design — retire the unproduced `FetchStatus.partial`

## The decision the bead asked for

`a2web-0br` states the branch explicitly: *remove `partial`, or give it a producer
if there is a state it should represent.* Both were evaluated against the code
rather than against taste.

### Option A — give `partial` a producer (rejected)

The state a `partial` would name is *"we retrieved something, but not all of what
was asked for."* That axis already exists and is already on the wire:
`retrieval_incomplete: bool`.

ADR-0019 traced it (`fetcher_response.py:728-784`) and found it **independent** of
`status`: several `status: failed` outcomes deliberately leave
`retrieval_incomplete` `False` — `gone_confirmed` (a corroborated dead URL is a
confident fact, not a miss), `operator_error`, `unreachable`. That independence is
load-bearing, and it is exactly what a `partial` status would destroy.

Concretely, giving `partial` a producer creates a two-axis encoding of one fact:

```
status=partial + retrieval_incomplete=true    agreement — redundant
status=partial + retrieval_incomplete=false   contradiction — undefined
status=failed  + retrieval_incomplete=true    the state that exists TODAY
```

Row 2 has no meaning anyone can state, and nothing would stop it being produced.
A caller then has to decide which axis wins. That is a worse contract than the one
being fixed, not a better one.

### Option B — remove it (chosen)

`FetchStatus` becomes `(ok, failed)`, which is:

- what every producer in `src/` has always written;
- what ADR-0019 already declares the field to be, in an **accepted** decision;
- one bit, which is all the field was ever asked to carry — the detail lives in
  `Verdict` (15 members), `TerminalOutcome` (7), `retrieval_incomplete`, and
  `operator_hints[].code`, all of which are already on or behind the wire.

## Why a guard test, and not just the deletion

Deleting the member fixes today. It does not stop the next enum member from being
added "for symmetry" or "reserved for later" and never wired — which is precisely
how `partial` got here.

ADR-0001 (*structural prevention over vigilance*) says the fix for a class of
defect is a structure that fails, not a habit of checking. The repository already
applies this to the sibling vocabulary: `test_every_hint_code_has_a_factory.py`
walks the source and asserts every declared hint code is actually built. This guard
is the same census applied to `FetchStatus`.

**Shape**, following that file's conventions:

- walk `SRC_ROOT` (from `tests/architecture/_walk.py`) and collect every
  `FetchStatus.<member>` attribute access that is a **producer** — an assignment or
  a return, not a comparison. A comparison (`status == FetchStatus.partial`) is
  precisely the dead-consumer code the defect creates, so counting it as a producer
  would make the guard vouch for the bug.
- assert every member of `FetchStatus` appears in that set.
- carry a **not-vacuous** check first — a walk that finds nothing would pass every
  assertion below it silently. The existing hint-code guard opens with exactly this
  assertion and it is the reason that guard can be trusted.

**Producer detection, stated precisely.** An `ast.Attribute` node whose value is
`Name("FetchStatus")` counts as a producer when its nearest enclosing statement is
an `Assign`, `AnnAssign`, or `Return` **and** the node is not inside a `Compare`.
This is deliberately conservative in the direction that fails loudly: a producer the
walk cannot recognise makes the guard fail, which is a visible prompt to teach it
the new form. A missed *comparison* would make it pass wrongly — hence the
`Compare` exclusion is the part that must be right.

## Contract-impact check, done before proposing

The bead directed checking the CLI contract and wire goldens first. Both were
checked, by search rather than by assumption:

- `grep -rn partial tests/contracts/` → no matches.
- `list_tools.json` parsed and searched for `partial` and `FetchStatus` → both
  absent. The served tool schema does not inline the status enum, so narrowing it
  does not move a golden.
- `grep -rn FetchStatus src/ tests/ docs/ openspec/specs/` → the only textual
  declaration of the three-member set outside `models.py` is
  `openspec/specs/app-composition/spec.md:17`, which this change's delta updates.

No `A2WEB_ACCEPT_WIRE_DELTA` re-bless is required. If `make check` disagrees, that
disagreement is the finding and the change stops rather than re-blessing a golden
to match.

## Alternatives not taken

- **Leave it and document it as reserved.** This is the status quo with a comment.
  A reserved slot on a live contract is indistinguishable, to a caller, from a state
  it must handle.
- **Generalise the guard to every wire enum at once.** `Verdict`, `Confidence`,
  `CacheState` are all produced today, so the guard would be green on arrival and
  the change would grow a census framework to prove nothing. Kept to the enum that
  actually failed; widening it later is a change with its own evidence.
