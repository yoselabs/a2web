## Context

Two defects surfaced together on one live `query` against a genuinely-dead URL
(real HTTP 404). They are unrelated in cause but mutually reinforcing in effect:
the jina defect made a dead page look retrieved, and the extraction defect
stripped away every field that would have contradicted that. The result was a
confident, success-shaped three-key envelope for a page that does not exist.

Both are drift against specs that already say the right thing. In each case the
spec's chosen *mechanism* is what failed, which is why the requirement text moves
with the code rather than the code simply being brought back into line.

Current state, established by direct measurement rather than reading:

- `curl` of the jina reader with a2web's own headers returns **3030 bytes**
  carrying `Warning: Target URL returned error 404: Not Found`; the same request
  without `X-Return-Format: markdown` returns **1467 bytes**. The decode guard
  fires below 2048. a2web's own request header is what disarms a2web's own guard.
- `grep -rn "request_routing=True" tests/` → **zero hits**. The flag combination
  `query` uses in production has never been executed by a test.

Constraints:

- `wire._TSV_FIELDS` and the frozen golden snapshots mean any envelope change is a
  contract change, subject to the `ask-response` wire gate and its accepted-delta
  discipline.
- The false-positive the length ceiling was defending against is real: a retrieved
  article that quotes the stub string must not be misread as a wrapper. Any
  replacement guard must keep that closed.
- CLAUDE.md: *never add a structural guard without an assertion that it found
  something*. Both fixes are guard-shaped, so both need non-vacuity.

## Goals / Non-Goals

**Goals:**

- One output contract per extraction call — the router path never also requests a
  fence.
- `answer` is fence-free on every path, including the degraded ones.
- A lost routing payload is visible to the caller instead of silently degrading.
- A wrapped upstream error is decoded at any body length, with the quoted-string
  false positive still closed.
- Test coverage at the exact flag combination and body size that production uses.

**Non-Goals:**

- Reworking `_confidence_for`. That `confidence: high` came from
  `(verdict, len(content_md))` alone is a real weakness, but once jina reports
  `not_found` truthfully the verdict is no longer `ok` and this case stops
  arising. Broader confidence hardening is follow-on work, noted in `BACKLOG.md`.
- Adding a `not_found` value to the obstacle enum. That would be a second,
  model-judgment backstop; the deterministic one is the one that should work, and
  this change repairs it. Adding an enum value is also an `ask-response` contract
  change deserving its own proposal.
- Changing `retrieval-completeness`. Its 404 story is correct and starts working
  the moment jina stops lying.
- Any change to the non-routing (`request_next_links` alone) path, which works.

## Decisions

### D1 — Suppress the fence suffix on the routing path, rather than teaching the parser to accept both

The next-links suffix is appended unconditionally at `extractor.py:213`, while the
fence stripper is an `elif` the routing path never reaches (`:270-279`). Two
repairs are available.

*Rejected:* make the routing parser fence-tolerant, accepting prose-plus-fence as
a valid response shape. This ratifies the contradiction — the model is still told
two incompatible things and the parser is made to cope. It doubles the accepted
input grammar at a boundary the wobble discipline exists to keep narrow, and every
future prompt change has to preserve both shapes.

*Chosen:* `request_routing` takes precedence in prompt construction; when it is
`True` the fence suffix is not appended at all. The model receives exactly one
contract. `other_pages` in the router schema already covers what the fence was
asking for, so nothing is lost — the fence request was redundant even before it
became harmful.

The flags stay independent in the signature (callers may set both, as `query`
does); only prompt construction resolves the precedence. This keeps the caller
side unchanged and localizes the fix.

### D2 — Strip fences on the routing branch too, as defense in depth

D1 removes the *cause*, but models emit stray fences unprompted, and the answer
field is the one every caller parses. The stripper moves out of the `elif` and
runs on both branches.

This is deliberately belt-and-braces: D1 alone would satisfy the observed bug, but
the guarantee we want to state in `ask-response` is "`answer` never carries a
fence", and a guarantee that holds only because the prompt currently behaves is
not a guarantee. Enforcing at the sanitization step makes it structural.

### D3 — Sanitize on the `ParseError` path instead of returning raw text

`except ParseError: return text, None` (`extractor.py:527`) returns the entire raw
model response as the answer. That is the direct mechanism by which the fence
reached the wire. The handler returns sanitized text.

Note this is a case where the spec was already aspirationally correct and the code
was not: `extraction/spec.md` says the answer "SHALL still be returned via the
existing extraction path" and its scenario says `answer` "still carries the
**successfully parsed** answer text" — the raw dump was never what was specified.
The delta makes the sanitization explicit so it cannot be read as optional again.

### D4 — Positional guard for the jina stub, not a length ceiling

jina's response has a stable two-region structure: a metadata header
(`Title:`, `URL Source:`, `Published Time:`, `Warning: ...`) followed by the
`Markdown Content:` separator and then the retrieved body. The wrapper stub is
*always* in the header; a quotation is *always* in the body. Position is the
actual discriminator; length was a proxy for it that happens to correlate on short
responses and fails on long ones.

Alternatives considered:

- *Raise the ceiling.* Picks a new arbitrary number with the same failure mode at
  a different page size, and widens the quoted-string false positive as it goes.
  Strictly worse in both directions.
- *Anchor the regex to the start of the response.* Nearly right, but brittle
  against field reordering or an added header field; scoping to the header region
  expresses the actual invariant rather than a positional accident.

Fallback: when no `Markdown Content:` separator is present, treat the whole
response as header and search it in full. jina emits the separator whenever there
is a body; its absence means there is nothing but wrapper.

### D5 — Surface the lost index by capping confidence plus an operator hint

A lost routing payload currently produces an envelope indistinguishable from one
where the page genuinely had nothing to index. ADR-0015 makes that distinction
load-bearing: the caller never sees the body, so it cannot recover the difference.

*Rejected:* fail the whole fetch. Far too harsh — the answer is usually fine, and
ADR-0009's floor is about unfetched content, not a degraded index over content
that was retrieved.

*Chosen:* the answer is delivered, `confidence` is capped below `high`, and an
operator hint names the loss. This matches the existing precedent in
`retrieval-completeness` for the structured-grounded carve-out: deliver the
answer, keep the honest hedge, direct the caller to verify — rather than a klaxon
that contradicts a usable result.

### D7 — A targeted bench subset, chosen by what D1 can actually break

The full matrix is 29 corpus cases × 3 systems × 3 LLM-judged axes. Under a quota
constraint that is not affordable, and most of it is not evidence about this
change anyway — the two extraction defects cannot affect baseline WebFetch
reproduction, and the quality/clarity axes are not where D1's risk lives.

The one thing D1 can plausibly break is link discovery: it deletes a
link-eliciting instruction and leaves `other_pages` to carry that need alone. So
the subset is chosen to hit exactly that:

- `--mode detail` — one system rather than three.
- `--axis next_links` — the single axis at risk. The deterministic token and
  contract axes always run regardless and are free, so contract conformance stays
  covered at no cost.
- Four slugs: `hn-front` and `gh-trending` (listing, link-dense) plus
  `hepsiburada-reviews-drilldown-on-page` and
  `amazon-product-reviews-elsewhere` (affordance — the class where the answer or
  its link lives on ANOTHER page, which is precisely the `drilldown` kind of
  `other_pages` that must now work without the fence).

Four cells instead of 261, aimed at the one hypothesis. Run as a before/after
pair around the D1 change so the comparison is meaningful rather than an absolute
score read against nothing.

*Rejected:* skip the bench entirely. D1 is a prompt deletion on the primary tool's
main path; landing that with zero output evidence is exactly the gap `make bench`
exists to close.

*Rejected:* full matrix. Correct if quota were free, and the right thing to run
before any release that bundles this. Noted as follow-up rather than a gate here.

**This is deliberately weaker evidence than a full run.** It tests one hypothesis
on four URLs. It would not catch a quality or clarity regression elsewhere in the
corpus, and the findings file must say so (task 7.4) so nobody later reads it as
full-matrix proof.

### D6 — Non-vacuity for both guards

Per the standing rule, each guard gets an assertion it found something:

- The jina regression pins a body **>2048 bytes** specifically, so a reintroduced
  ceiling fails the test rather than passing vacuously.
- The extraction test asserts on the rendered prompt (fence instruction absent)
  rather than only on the parsed output, so a refactor that stops appending for an
  unrelated reason still exercises the real assertion.
- The `request_routing=True` + `request_next_links=True` combination is added to
  the test matrix, closing the zero-hit grep that let this ship.

## Risks / Trade-offs

- **[The header-region assumption is jina's format, which can change]** → Same
  exposure class as the existing regex, not a new one, and strictly narrower than
  the length ceiling it replaces. Mitigated by the fallback (no separator ⇒ search
  whole response) and by the corpus entry, which exercises the real reader
  live and will surface a format change as a corpus failure.

- **[Removing the fence request changes model behaviour on the routing path]** →
  `other_pages` covers the same need and is the documented field; the fence was
  redundant. Risk is that some models populated links better via the fence than via
  the schema field. Mitigated by the targeted bench subset in D7 — four
  listing/affordance slugs on the `next_links` axis, run as a before/after pair —
  rather than the full matrix. Residual risk accepted: a regression outside those
  four URLs would not be caught.

- **[Capping confidence on lost routing is a wire change]** → It moves a value on a
  degraded path only, and the golden gate will flag it. The delta gets a recorded
  reason in the accepted-delta table per the existing discipline. Callers keying on
  `confidence: high` see strictly fewer false highs, which is the intent.

- **[Truthful jina 404s change tier routing]** → A previously-`ok` jina result now
  reports `not_found`, so the ladder continues and may escalate to browser where it
  previously stopped. On the served container there is no browser, so these
  resolve as `gone_unverified` rather than `gone_confirmed` — honest, correctly
  hedged, and still a large improvement over `ok`/`high`. Some fetches get slower
  because they now do the work a laundered `ok` was skipping; that cost is the
  point.

## Migration Plan

No data migration. Deployment is the standard path: land on `main`, rebuild the
`Dockerfile` image, owner-driven redeploy on Shen.

Rollback is a straight revert — the change is behavioural, with no persisted state
shape change. One caveat: cache entries written while jina was laundering 404s may
hold `ok` bodies for dead URLs. The cache is keyed `(url, profile_hash)` and TTL'd,
so these age out; no forced invalidation is proposed, but if a stale-404 report
arrives, clearing the cache dir is the remedy.

## Open Questions

- Which operator hint code names the lost index? Reusing `retrieval_incomplete`
  overloads a code that currently means "content was not retrieved", which is not
  what happened. A new code is likely correct but adds to the `ask-response`
  surface. Resolve during implementation, defaulting to a new dedicated code.
- What exact confidence value does a lost index cap to — `medium`, or straight to
  `low`? `low` matches the structured-grounded precedent but may over-hedge an
  otherwise good answer. Defaulting to `medium` unless the bench shows otherwise.
