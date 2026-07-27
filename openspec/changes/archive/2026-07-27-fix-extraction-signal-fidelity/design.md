# Design

## Evidence base

Every decision below is anchored to a measurement, because the previous attempt
at this problem was anchored to a fixture and got the answer backwards.

| finding | how measured | n |
|---|---|---|
| routing recovered on healthy pages | live spike, extractor seam, subscription provider | 5/5 |
| routing recovered on degenerate pages (404s, thin, error) | live spike, chosen to falsify "unparsable correlates with degenerate" | 5/5 |
| model wraps envelope in a ` ```json ` fence | both spikes | 15/15 |
| healthy extraction emits `llm_wobble` | offline, canned envelope | 5 events per call |
| wire index delivered end-to-end | live spike, full pipeline | 3/5 |

The `unparsable` population was largely *created* by the double-contract defect
fixed in `bc52b4c` (the router template and the next-links suffix asked the
model for two contradictory output contracts) and largely *deleted* with it. The
exact `bhklima.com` 404 that motivated the original report now recovers cleanly.

## D1 — `OPTIONAL` is a new tolerance, not a flag on `DEFAULT`

The four-value vocabulary cannot express "absent is normal". `DEFAULT` today
fires both when a field is missing and when it is malformed, and logs both. The
split has to happen in the vocabulary because the *caller* is what knows whether
a field is optional — the funnel cannot infer it.

Placement: shelf `llm-wobble`, as an EVOLVE (additive; existing tolerances keep
their behaviour, so resolution 0007 monotonicity holds). The alternative —
filtering the log downstream in a2web — was rejected: it leaves the funnel
emitting a wrong event and adds a second mechanism to suppress it, which is the
redundancy the constraint forbids.

**Risk:** every existing `DEFAULT` field must be triaged as genuinely-optional
vs present-but-malformed. Mis-triaging one direction restores the noise;
mis-triaging the other hides a real recovery. The triage table goes in
`_policies.py` next to the tolerances, and each entry carries the reason.

## D2 — `RoutingOutcome` replaces the bool outright

```python
class RoutingOutcome(StrEnum):
    RECOVERED = "recovered"
    UNPARSABLE = "unparsable"      # no envelope even after fence tolerance
    UNCLASSIFIED = "unclassified"  # envelope good, classification absent
    PROVIDER_ERROR = "provider_error"
```

`routing_lost` is deleted. No deprecation window, no parallel field — a
compatibility shim here would preserve exactly the conflation being removed.

`provider_error` is a member rather than being excluded from the type, because
the extractor genuinely reaches that state and a type that cannot express it
pushes the distinction back into ad-hoc booleans at the call site. Its
*consumers* exclude it.

## D3 — Decoupling: parse the index before returning on classification

Today `_build_router_payload` returns `payload=None` on a missing
`structural_form` **before** reaching the `also_here` / `other_pages` parsing.
The fix reorders: parse the index unconditionally, then decide what the
classification-dependent consumers get.

The options-shelf gate stays exactly as strict. It exists for a real regression
(a product page's site-wide footer megamenu parses into a plausible record set
and leaked 10 junk entries), and nothing here relaxes it — a `None`
classification suppresses the shelf just as a `product` classification does.

## D4 — The hint is gated on the DELIVERED index, not on routing loss

This is the load-bearing correction, and it came from the full-pipeline spike.
The wire index has **three** sources:

1. the LLM routing payload (`also_here`, `other_pages`)
2. DOM-mined `next_links`, folded into `other_pages`
3. the DOM-mined `options` shelf

Routing loss removes only source 1. On HN the LLM supplied zero `other_pages`
while the wire carried a populated `other_pages` block from source 2 — so a hint
gated on routing loss would have fired on a response that left the caller a
perfectly good index. Gating on "the delivered index is empty" is the condition
that actually matches the ADR-0015 harm.

## D5 — What is NOT built, and why

**No status promotion.** `failed` + `retrieval_incomplete` steers callers toward
`try_user_browser` and re-fetching; it would prescribe browser escalation for a
page fetched perfectly, to fix a formatting artifact a re-fetch cannot touch.
Status describes retrieval; hints describe extraction degradation.

The pull toward failing came from ADR-0015's "same class of harm as a silent
miss" sentence. Same *class*, not same *magnitude* — and a2web's own
empty-vs-wall doctrine already encodes the asymmetry: over-warning is cheap, a
confident silent miss is expensive. A loud warning is the over-warn side.
Failing a response that carries a good answer discards value to feel safe.

**No retry rung.** Its economic justification was false: `_phase_cache_check`
serves a same-URL re-query from the HTTP cache within TTL, so a client-side
retry costs one LLM call — about what a server-side re-ask costs. The rung buys
latency, not proxy budget. And with the double-contract defect fixed there is
little left to retry.

**No `include_content` conditional.** With both arms as hints it collapses to at
most a severity tweak. It would also have made the same page and model produce
different statuses based on a display flag, and `include_content=True` is the
rare path — a chronically under-exercised branch, which is exactly how the
fixtures went dark.

**No constrained decoding.** Correct in principle and it would delete
`unparsable` structurally, but `anyllm` exposes no `response_format` /
`json_schema` / `tool_choice` today, and the two `claude-code` adapters — the
ADR-0016-mandated dev/bench default — likely cannot expose it at all. So it
could not cover the default path. Recorded in `BACKLOG.md`, not built.

## D6 — Sequencing

`restore-llm-fixture-fidelity` MUST land first. Its replay harness rebuilds
`ExtractionResult` with no routing, so all 16 replayed cases currently run the
degraded branch. Landing this change first would bless goldens around that lie
for the second time in one week.

## Open question

The full-pipeline spike found `arxiv.org/list/cs.CL/recent` delivering a
distilled answer with **no index from any of the three sources** — a genuine
ADR-0015 gap, and a different one than this change addresses. At n=5 with high
run-to-run variance it is a lead, not a verdict. Captured as corpus case
`listing-answer-always-leaves-an-index` so it cannot be lost, and left for a
separate change once the fixture work makes it measurable.
