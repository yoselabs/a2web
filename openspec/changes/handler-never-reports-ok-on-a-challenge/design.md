## Context

Handlers are tier-0. They fetch with their own transport, extract with their own
knowledge of the site, and hand the orchestrator a `TierResult` carrying a
verdict. The gate runs afterwards on the rendered `content_md`, so a handler that
lies has a backstop.

The backstop is not a guarantee, and this case shows exactly where it thins out:

```
handler says ok ──▶ gate evaluates content_md ──▶ wall? ──▶ escalate / fail loud
                         │
                         └── only consults _BLOCK_PATTERNS when
                             len(content_md) < LENGTH_FLOOR
```

The twitter interstitial renders to 416 characters, so it falls inside that
branch and the gate catches it — but only since the fingerprint landed hours
ago, and only because this particular interstitial is short. A wordier one from
the same vendor family renders past 500 and the gate returns `ok`.

So "the gate will catch it" is true today by two coincidences. The handler is
the component that knows it asked a nitter instance for a tweet and got a
challenge; that knowledge should not have to survive a round trip through a
length heuristic.

## Goals / Non-Goals

**Goals**

- A handler that received a challenge page says so.
- A walled upstream in a failover list does not shadow the upstreams after it.
- When every upstream is walled, the caller gets the ADR-0009 treatment: loud,
  explicit, `retrieval_incomplete`, critical hint.

**Non-Goals**

- Making the twitter handler succeed. No reachable nitter instance exists
  (10 surveyed). This change is about truthfulness, not availability.
- Broadening the block catalogue. The pattern set is what it is; this change
  consumes it from a new place.
- Removing the gate's own check. Two independent readers of the same evidence is
  the intent, not duplication to be collapsed — see D2.

## Decisions

### D1 — The check goes in `handlers/_common.py`, consuming `block_detector`

`_common.py` already owns the shared handler vocabulary (`empty_result`,
`map_non_ok`). The challenge check joins it as a third helper rather than being
inlined per handler, for the reason the four-way `Rendered` install duplication
taught: a second inline copy is how two copies disagree.

It consumes `packages.block_detector.evaluate`. **No handler imports from
`packages/` today, so this is a new seam edge** — allowed by `tach.toml`
("domain code may freely import from any package"), but worth naming rather than
discovering later. The alternative, re-implementing a fingerprint check inside
`handlers/`, would put a second wall catalogue in the tree, which is strictly
worse: the catalogue's value is that it is one bounded list with one set of
witnesses.

### D2 — The handler check does NOT replace the gate check

Two components now ask "is this a wall?" of the same page. That is deliberate.

They ask it at different times with different information. The handler asks
before it has decided anything, and can act by trying another upstream — an
option the gate does not have, because by the time the gate runs the failover
loop is over. The gate asks about whatever content finally arrived, from any
tier, including tiers with no handler at all.

Collapsing them would mean either the gate loses coverage of non-handler tiers,
or the handler loses the ability to fail over. Neither is a simplification.

The cost is that a walled page can be fingerprinted twice. It is not double
counted — the handler returns non-`ok` and the tier loop moves on.

### D3 — A walled instance is a failed instance, not an answer

The heart of the change, and the part that outlives the current upstream
drought:

```python
# before                              # after
if verdict == Verdict.ok:             if verdict == Verdict.ok:
    return result   # ← walled            return result   # challenge → not ok
                                      #   ↓ so the loop continues
```

`_try_instance` classifies its own response, so a challenge becomes
`Verdict.block_page_detected` there, the existing `_NitterInstanceFailure` path
registers it with that instance's circuit breaker, and the loop advances. The
breaker registration is a bonus that falls out for free: a persistently walled
instance gets tripped rather than re-tried every fetch.

Note what this does NOT do: it does not rank instances or prefer one. It removes
a false positive from an existing failover, nothing more.

### D4 — Keep the handler, do not retire it

Retirement was the live alternative, and the survey is what argued against it —
not sentiment about the code.

Measured, both ends:

```
handler present, walled upstream   status=failed  block_page_detected
                                   retrieval_incomplete=True
                                   hints=[try_user_browser (critical)]

handler absent (no_match)          status=failed  not_found
                                   hints=[content_not_found (info),
                                          browser_unavailable (info)]
```

The walled answer is the more useful one. `try_user_browser` at `critical`
tells the caller the URL was blocked and what to do; `content_not_found` at
`info` says the page might not exist, which is false. Retiring the handler
would trade a correct loud failure for a quiet wrong one.

*Caveat on that measurement, stated because it weakens the comparison:* the
handler-absent run had no browser available in this environment, so the cascade
did not exercise the browser tier. A production run with a browser might reach
x.com directly and do better. That would be a reason to revisit — it is not a
reason to retire the handler while its failover bug is unfixed, because the bug
would come back with the next working upstream.

If the instance survey is still at zero working after a reasonable interval,
retirement becomes the right call and should be its own change with its own
survey.

## Risks / Trade-offs

- **A false-positive challenge match makes a handler skip a good upstream.** The
  catalogue's markers are tight and length-gated, and the failover means a false
  positive costs one extra request rather than a failed fetch. Acceptable.
- **`habr` and `wikipedia` gain a check that may never fire.** Neither has been
  observed serving a challenge. The value is symmetry — a check present only
  where a defect was observed is a check nobody remembers to add next time.
- **The twitter handler still cannot succeed.** Its probe case and corpus cell
  stay red. That is the honest state, and both are annotated as expected-red.
- **Two wall readers can diverge** if one is updated and the other is not. They
  share the catalogue, so divergence would require changing the branch structure
  rather than the patterns.

## Open Questions

- **Should the wall check apply to `pre_rendered` handlers generally, at the
  tier seam rather than per handler?** That would cover every current and future
  handler in one place. It is the better shape and it is a bigger change —
  `SiteHandlerTier` would need to distinguish "handler declined" from "handler
  retrieved a wall". Worth doing if a fourth handler needs the check.
- **Does any nitter instance work from a residential IP?** The survey ran from
  one network. A proxy-routed survey might find one, which would change D4's
  arithmetic but not the failover fix.
