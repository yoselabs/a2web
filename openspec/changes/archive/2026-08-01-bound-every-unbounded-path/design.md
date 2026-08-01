## Context

Three unbounded paths, verified 2026-07-31. They share the property that the
input driving them is chosen remotely, and none of the three has a bound that an
operator can see or change.

The single most useful measurement taken while scoping this: `settings.py`
carries exactly ONE timeout knob, `browser_idle_timeout_s`, and it governs
browser idleness rather than any request bound. So the answer to "how long can a
`query` take?" is currently *unknown, and not adjustable*.

## Goals / Non-Goals

**Goals**

- A single answerable ceiling on a fetch, set by the operator.
- No path that can hang the tool call indefinitely.
- The `hn.py` recursion bounded on every path, including the one a naive cap
  misses.

**Non-Goals**

- Retuning the existing 34 per-hop timeouts. They are individually reasonable;
  the defect is that nothing composes them.
- Fixing `anyllm`. The shelf gap is real and is filed, but this change ships
  a2web's own seam so the hang is closed now.
- A general cancellation architecture. `asyncio.timeout` at the orchestrator is
  sufficient and spends no magic budget.

## Decisions

### D1 — The deadline lives on `FetchContext`, as remaining budget

A single `deadline` (monotonic) is set at `fetch()` entry and read wherever a
hop is dispatched. Each hop receives `min(its own timeout, remaining)`.

Chosen over a wall-clock total checked between phases, because a check *between*
phases cannot interrupt a hop that is itself the thing overrunning — which is
the common case, since the long hops are browser renders and LLM calls.

Interaction with T1: `FetchContext` is the object T1 phase two will slice
per-node. The deadline is a single scalar read by many nodes, so it belongs in
whatever survives as the shared context. This change should not be blocked on
that decision, and does not constrain it.

### D2 — The LLM bound is enforced at a2web's seam, and says so

`anyllm.LLMProvider.complete()` takes no timeout. Wrapping the call in
`asyncio.timeout` cancels a2web's coroutine; whether the adapter's underlying
HTTP request is actually aborted depends on the adapter, and for the
subscription CLI/SDK backends it likely is not.

So the failure must be worded honestly: *a2web stopped waiting*. Claiming the
upstream request was cancelled would be a statement a2web cannot verify — the
same class of error as asserting a wall on evidence-free thinness.

The real fix is a timeout parameter on `anyllm`. Filed as a shelf promotion,
deliberately not bundled: it would make this change wait on a dependency bump
for a defect that can be closed today.

### D3 — `hn.py` copies its siblings rather than inventing a third answer

`habr.py` and `discourse.py` both use `_MAX_DEPTH = 20`; `habr.py` additionally
carries `_MAX_COMMENTS = 400`. `hn.py` gets the same two constants with the same
names and values.

Not a shared helper, and not yet a promotion: three near-identical
tree-renderers is exactly the rule-of-three trigger, but consolidating them is
T5/T7 work with a real design question (`habr.py` threads its budget as a
one-element list used as a mutable counter, which is not the shape to
generalise). Closing the security hole should not wait on that.

**The deleted-comment path is the substantive part.** `hn.py:240` recurses with
`depth=depth`, so depth does not advance through a chain of deleted comments and
a depth cap alone would not terminate. The fix advances depth on that path too.

### D4 — Crossing a bound is an ADR-0009 failure, not a truncation

Every new bound, when crossed, produces `status: failed` +
`retrieval_incomplete: true` + an operator hint. This is the existing floor, and
the alternative — returning what was gathered so far, quietly — is precisely the
confident silent miss the floor exists to prevent.

The handler tree bound is the one exception in kind: a truncated comment tree is
a real partial result with real content, so it declares its truncation in the
render (as `arxiv.py` already does for listings) rather than failing the fetch.

## Risks / Trade-offs

- **A deadline that is too short converts slow successes into failures.** The
  default must be set above the observed worst-case ladder walk (~329 s of
  composed hops), not at it. A bound pinned at the observed value is a golden and
  fails on the first slow day.
- **The LLM timeout may not free the upstream resource.** Accepted and stated in
  the spec. a2web's obligation is to return; the provider's resource lifetime is
  the provider's.
- **Threading remaining-budget through hop dispatch touches the tier seam**,
  which T1 will move. The change is small (one argument at the dispatch sites)
  and the alternative is leaving the hang open until after a multi-week refactor.

## Open Questions

- Default deadline value. Should be derived from the measured worst case rather
  than chosen; measure before setting.
- Does the deadline apply to `fetch_raw` as well as `query`? Probably yes with a
  lower default, since `fetch_raw` runs no LLM — but that is two knobs, and two
  knobs is a decision to make deliberately.
- Whether the hn depth/count constants should be settings or literals. The
  siblings use literals; consistency argues literals, the request-bounds
  requirement argues settings. They are not request bounds, so literals is
  probably right.
