## Context

Five independent ADR-0009 leaks, verified by direct execution and source
reading on 2026-07-31. They are grouped into one change because they share a
single failure shape — *a2web knows more than it tells the caller, and what it
tells reads as success* — and because four of the five are one-site fixes whose
cost is dominated by writing the witness, not the fix.

They do NOT share code. The change can be applied in any order and each task is
independently revertible.

## Goals / Non-Goals

**Goals**

- Every one of the five leaks closed, each with a witness that fails before the
  fix and passes after.
- Each witness reads the channel the defect lives in. This is the load-bearing
  constraint: the TSV defect survived seventeen rounds of wire review because
  every existing assertion read `structured_content`.

**Non-Goals**

- Restructuring `wire.py`, `models.py`, or the handler tree. That is T1/T5.
- A general audit of the other silent-swallow sites (16 found, 11 on a retrieval
  path). Only `github.py`'s six are in scope, because they are the ones that
  reach the caller as `Verdict.ok`.
- Migrating a2web's whole exception vocabulary to `a2effect`. Scope is the
  errors that are already operator faults today.

## Decisions

### D1 — Union of keys, not first row, and not a literal column table

`_TSV_FIELDS` is deliberately literal because *which fields become tables* is a
contract and inference is how a wire change happens by accident. **Which columns
a given table has is not the same question.** Rows are heterogeneous by
construction (`_omit_default_severity`), the key set is a property of the data
rather than of the contract, and a literal per-field column table would need a
maintained entry for every model whose serializer elides a field — which is the
condition that produced three divergent hand-rolled helpers in `models.py`
already.

So: union of all rows' keys, first-seen order. This is also what the three
`models.py` helpers are each approximating, which is why they collapse into it.

Rejected — *drop the conditional elision instead* (always emit `severity`).
That fixes the wire at the cost of putting a dead `severity: info` on every hint
in `structured_content`, which is the noise `_omit_default_severity` exists to
remove. The elision is right; the encoder was wrong.

### D2 — `github.py` declares, rather than fails

Six degrade sites, each supplementary to a primary object (a repo's issues, an
issue's comments). Failing the whole fetch because the issues list was
rate-limited would be worse than the present behaviour: the primary content was
retrieved and is useful.

The fix is therefore an operator hint naming the unretrieved section, plus
**not** rendering the section as empty. A section that could not be retrieved
must be visibly absent-because-unretrieved, never absent-because-empty.

`github.py:226` is a separate bug in the same family and is included: it catches
only `BadRequest` for the README where four sibling guards catch
`GitHubException`, so a rate-limited README aborts the whole repo fetch — the
opposite failure, over-failing where the others under-fail.

### D3 — The challenge check is enforced by a guard, not by review

Adding the call to `_fetch_old_reddit` fixes today's instance. The guard is what
makes it a property: an AST test asserting that every handler path calling a
generic prose extractor on retrieved HTML also calls `challenge_verdict`.

Per the anti-vacuity rule, the guard must assert it found candidates — a walk
that matches zero extractor calls reads identical to a passing one.

### D4 — Type only what is already an operator fault

Three concrete sites: `LLMNotAvailable` (no provider configured),
`ResourceUnavailable` (a declared resource could not be entered), and the paid
tier's authentication failure. Each becomes the appropriate `a2effect` subclass.

Everything else stays as it is and continues to quarantine into
`UnexpectedDefect`, which is correct for it.

The scenario requiring a test to drive the `except AppError` branch is the
anti-vacuity clause applied to this fix: without it, the branch returns to being
unreachable the moment the last typed raise is refactored away.

### D5 — The terminal-hint guard's allowlist entry is the finding, not a detail

`test_terminal_hint_coherence.py:33` maps `operator_error` to `frozenset({None})`
with the comment "paid_auth_error hint emitted at the paid tier". No such hint
is emitted. The guard is green because it was told to expect nothing, on the
strength of a claim nobody checked.

Once the hint exists, that entry must become an assertion that it is present.
Leaving it as an allowlist would keep the guard green through the hint's
deletion — which is exactly the state being fixed.

## Risks / Trade-offs

- **The TSV column change alters the `content[0].text` bytes** for any envelope
  with heterogeneous rows. That is the point, but it means golden/contract
  captures over that channel will move. Re-blessing them is part of the change,
  and each re-bless must be inspected rather than accepted wholesale — a
  re-bless is how a wire regression goes green.
- **Union-of-keys widens tables.** A table where one rare row carries an extra
  key now costs an empty cell on every other row. Measured against the
  alternative — silently dropping the rare row's data — this is the right trade,
  and the affected fields are small (hints, links, options).
- **`github.py` gains hints on partial degradation**, so some previously-quiet
  responses now carry an operator hint. This is a deliberate increase in
  loudness on the ADR-0009 asymmetry: over-warning is cheap, a confident silent
  miss is not.

## Open Questions

- Should the unretrieved-section hint be a single code with a section name, or
  one code per section? A single code with the section in `message` keeps the
  hint catalogue from growing per-handler; decide at implementation.
- `a2effect`'s five classes are `AuthError`, `InfrastructureError`,
  `InputError`, `PolicyError`, `UnexpectedDefect`. `LLMNotAvailable` is arguably
  `PolicyError` (a2web declined to spend) or `InfrastructureError` (a dependency
  is absent). Resolve against `a2effect`'s own definitions before typing it.
