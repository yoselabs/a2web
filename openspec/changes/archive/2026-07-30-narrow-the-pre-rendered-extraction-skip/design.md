## Context

This is the second half of a fix whose first half landed and was measured not to
work. The chronology matters because the measurement is the only reason we know
where the real gate is:

```
2026-07-28  restore-links-on-pre-rendered-tiers ships:
              fc.links populated on the pre-rendered path, six trafilatura
              bypasses funnelled, Rendered.links added, funnel guard landed
2026-07-28  eval/runs/post-link-fix (16 cells, claude-code-sdk):
              listing-answer-always-leaves-an-index  unscored → unscored
              reddit-listing                         unscored → unscored
              i.e. the fix was NECESSARY AND NOT SUFFICIENT
```

What that run did prove: the arXiv envelope gained `title` and `byline`,
`headings` went 0 → 4, and the canonical extractor returns 484 links on that
page. The seam is genuinely closed. `other_pages` is blocked further down.

The full skip, read as a call graph:

```
_phase_extract                                          fetcher.py:1265
  raw_html = fc.body.decode(...)                        fetcher.py:1268
  if fc.pre_rendered_payload is not None:
      copy content_md, title, byline, headings, links
      RETURN                                            fetcher.py:1285
                                                          │
      ┌───────────────────────────────────────────────────┘
      │  everything below is unreachable on browser / archive /
      │  jina / zyte / firecrawl / all 9 handlers
      ▼
  extract_markdown(raw_html, …)          ← trafilatura.  THE OPTIMISATION.
  parse_metadata(raw_html)               ← also fine to skip
  _run_extraction_escalation(…)          ← json_in_html + record_mine.
  _phase_listing_completeness(…)         ←   NOT trafilatura. NOT the optimisation.
```

`_run_extraction_escalation` sets `fc.content_candidates`, `fc.record_count`,
`fc.record_set` and `fc.next_links_handler`. `_build_link_digest` reads
`content_candidates`; `_phase_listing_completeness` reads `record_count`; the
option shelf reads `record_set`. Four consumers, one skip, and the skip is named
after a fifth thing it is correctly skipping.

## Goals / Non-Goals

**Goals**

- The structured ladder is entered on every path that holds HTML, not on the
  path that happened not to have a `pre_rendered` payload.
- `other_pages`, `listing_partial` and handler `next_links` become emittable on
  the hard-fetch population — measured, not asserted, by re-running the same
  cells that measured the last attempt failing.
- The `pre_rendered` optimisation survives intact and is pinned by the same
  guard that pins the ladder, so the next narrowing cannot quietly widen.

**Non-Goals**

- Touching `_DIGEST_GATE_SOURCES`. See D2.
- Recovering structure from jina's markdown or from the JSON-API handlers. Both
  deferred by the previous change and still deferred; D3 explains why running
  the ladder over their bodies is nonetheless the right no-op.
- Any change to the extractor prompt, `RouterPayload`, or handle rehydration.
- Any change to the measurement layer. `close-silent-eval-loss` surfaced this
  chain; the two stay independently verifiable.

## Decisions

### D1 — Narrow the skip to content extraction; do not widen anything else

The pre-rendered branch keeps skipping `extract_markdown`, `parse_metadata` and
the date finders — a tier that already produced markdown must not pay
trafilatura twice, which is the entire reason `pre_rendered` exists. It stops
skipping `_run_extraction_escalation` and `_phase_listing_completeness`, which
are different parsers over the same bytes.

The baseline candidate is seeded from the pre-rendered markdown rather than from
trafilatura's output:

```python
fc.content_md = fc.pre_rendered_payload.content_md
… title, byline, headings, links …
await _run_extraction_escalation(fc, raw_html=raw_html)   # seeds from fc.content_md
_phase_listing_completeness(fc, raw_html=raw_html)
return
```

`_run_extraction_escalation` already opens with
`if fc.content_md: candidates.append(ContentCandidate(source="trafilatura", …))`
— it reads `fc.content_md`, not a return value from `extract_markdown` — so
seeding is what already happens once the assignment is above the call. No new
branch. The `source="trafilatura"` label becomes mildly inaccurate on this path
(the markdown came from the tier, which for browser/archive/wikipedia *did* come
from `extract_markdown` inside the tier, and for the handlers did not). Renaming
that literal is a wire-visible change to the candidate menu and belongs in its
own change if it is worth doing at all; noted, not done here.

*Alternative rejected:* a separate `_phase_structured(fc)` called from
`_run_pipeline` after `_phase_extract`, so both paths converge outside the
branch. Structurally cleaner and it is what a fresh design would do. Rejected
because it moves the call site for the raw path too, changing the order in which
`fc.content_md` is assigned relative to the diagnostics row and the
`extract_dur_ms` accounting — a refactor with its own regression surface,
bundled into a change whose entire value is one measurable behaviour delta. If
the branch grows a third divergence, revisit.

### D2 — `_DIGEST_GATE_SOURCES` is not the defect and is not touched

The previous change's Open Questions asked whether the gate was still right,
having found it standing behind the link fix. Answer: yes, and it was never the
thing in the way.

The gate requires a `json_synth` or `record_synth` candidate as a pre-LLM proxy
for `structural_form ∈ {product, listing}` — which is exactly what
`link-affordances` requires ("The digest SHALL be assembled only for pages
classified `structural_form ∈ {product, listing}`; other genres SHALL NOT incur
the digest cost"). Relaxing it would put a digest on prose articles, spending
tokens the envelope-diet work fought for, to satisfy a spec requirement that
explicitly says not to.

The gate was unsatisfiable on the pre-rendered path because the candidates that
satisfy it were never produced. Produce them and the gate does its job. Fixing
the gate would have been fixing the symptom one layer down — the same mistake as
the two wrong diagnoses this investigation already filed.

### D3 — Run the ladder unconditionally; let each rung self-gate on the body

`fc.body` is heterogeneous across pre-rendered tiers:

| tier | `body` | `json_in_html` | `record_mine` |
|---|---|---|---|
| browser | `page.html` — the rendered DOM | yes | yes, and on *better* HTML than the raw tier sees |
| archive | cleaned snapshot HTML | yes | yes |
| wikipedia, reddit-HTML | upstream HTML | yes | yes |
| reddit-API, hn, arxiv, … | JSON | no payloads | no records |
| jina | markdown bytes | no payloads | no records |

A content-type precondition is tempting and is not added. The ladder's stated
contract is that **each rung self-gates on its own preconditions** — that is a
requirement in `extraction`, not an implementation accident, and it is the
reason a clean article already reaches the record rung and gets nothing. A
non-HTML body is one more input on which the preconditions do not hold. Adding a
second, outer gate would duplicate that judgement in a place where it can drift
out of agreement with the rung.

The cost of the no-op is a selectolax parse of a non-HTML string and a scan for
`<script>` tags that are not there. That is the measurement in task 4, not an
assumption — if it turns out to be material on the JSON handlers, the fix is a
precondition inside the rung, where the rest of its gating already lives.

Note what this buys on the browser tier specifically: `record_mine` runs over
the *post-JavaScript* DOM. A listing that renders its items client-side — the
exact population that forced a browser fetch — has never once been through
record detection. This is the first time those pages are structurally parsed at
all.

### D4 — One guard, both halves of the boundary

The test asserts, on a single pre-rendered fetch of listing-shaped HTML:

1. a `record_synth` candidate is present in `fc.content_candidates`
2. `_build_link_digest` returns non-`None`
3. `fc.record_count` is set and commensurate with the fixture's item count
4. the diagnostics list still contains **no `extract` row**

(4) is not decoration. It is the half of the boundary that must not move, and
separating it into its own test invites a future edit to satisfy 1–3 by deleting
the branch. The fixture carries a known item count so (3) cannot pass vacuously
on a single stray record — the same non-vacuity discipline as the anchor-count
floor in the previous change, which is the repo's standing rule for structural
guards.

Watched failing before the fix, per the same rule.

## Risks / Trade-offs

- **Latency on the slowest tiers.** Two extra parses per pre-rendered fetch, on
  the population that is already paying for a browser. Measured in task 4
  against the same corpus subset, and the change does not ship if the delta is
  material without a rung-level precondition to go with it.
- **Token cost rises, again.** A populated digest adds prompt tokens on pages
  that previously sent none, and this change makes that real on the population
  the last one failed to reach. The token axis scores it.
- **`other_pages` quality on browser-served pages is still unmeasured.** The
  `next_links` axis has one prior observation ever (mean 3.17, 2026-07-28) and
  none on this population. Expect poor first numbers; they are a baseline, not a
  regression. This risk was carried by the previous change, was never actually
  taken because the fix did not land the behaviour, and is inherited unchanged.
- **`listing_partial` fires somewhere it never has.** An infinite-scroll listing
  served by the browser will now be told it is partial. That is correct and it
  is also a new failure-shaped signal on pages that previously returned a
  confident `ok` — which is the point, but it will look like a regression in any
  metric that counts `ok`s.
- **The `source="trafilatura"` label is now sometimes a lie** on this path. Wire-
  visible, deliberately not fixed here (D1), and it will confuse the next person
  reading a candidate menu from a handler fetch.

## Open Questions

- **jina's markdown.** Its `](url)` targets are recoverable with a different
  parser. Deferred from the previous change, still deferred, now with one more
  reason to want it: jina is the only tier that will still reach zero rungs on
  HTML-bearing content.
- **The JSON-API handlers.** `reddit` and `hn` know their permalinks and record
  structure natively and could populate `record_set` with better precision than
  any parse of their JSON. Unchanged from the previous change's open question,
  and this change deliberately does not answer it — the ladder no-ops on them,
  which is honest, not a fix.
- **Should the escalation move out of `_phase_extract` entirely?** D1's rejected
  alternative. Worth doing when there is a third caller or a third divergence,
  not before.
