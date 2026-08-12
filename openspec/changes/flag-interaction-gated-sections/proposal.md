## Why

a2web reported an absence that the fetched page contradicts. A query for seller
Q&A against a Hepsiburada product page returned `confidence: high` with *"No
seller Q&A or question-answer content is present on this page"* — while the
retrieved page states, in its own text, `Soru Cevap` / `4`.

The Q&A body sits behind a `<button>` with no `href`; activating it does not
change the URL (verified by live probe), and no browser backend a2web can reach
is able to click. So there is no URL to follow and no rung to escalate to — and
today there is no way for the envelope to say *"this section exists and we did
not retrieve it."* Everything collapses into "not present."

Three `AGENTS.md` rules already forbid this shape (never discard a producer's
own claim; never declare against a source-stated total; never render a degraded
sub-fetch as absent-at-source). None of them was reachable from a generic tier.
ADR-0020 states the tenet; this change wires it.

## What Changes

- **Detect click-gated sections deterministically, from raw HTML.** A new
  sufficiency phase inspects `fc.body` for disclosure widgets whose panel is
  absent or empty (`role="tab"` + `aria-controls`, `aria-expanded="false"`,
  `<details>` without `open`), capturing each gate's visible label and any
  adjacent source-stated count. It reads raw HTML, **not** `content_md`: the
  discriminator is markup, and the converter on the tier that serves this page
  (trafilatura, on `raw`) drops such tab strips entirely.
- **Let the extractor judge relevance.** Detected gates are injected into the
  extractor's input as grounded handles — the same closed-set mechanism page
  links already use (ADR-0013) — and the model selects which gate, if any,
  blocks the current question. A deterministic term-overlap test cannot do this:
  the motivating case has zero token overlap between `seller Q&A questions and
  answers` and `Soru Cevap`.
- **New operator-hint code `interaction_required`** (`severity: warning`),
  naming the section, relaying the source-stated count, and stating explicitly
  that **no other URL exists** and **re-querying this URL is futile**.
- **Cap `confidence` `high → medium`** when a gate blocks the answer, mirroring
  the three existing caps (`served_url_differs`, `query_title_mismatch`, failed
  browser rung).
- **Declare `confidence` and the hint branching surface.** `Confidence` gains a
  docstring ("retrieval quality, not answer trust") and the `query` tool
  description gains one sentence on each. Today neither is documented where a
  caller can see it, which is why `low` is read as "retry".
- **NOT changed:** no new envelope field, no `retrieval_incomplete`, no
  `confidence: low`, no auto-navigation to another URL. Each is rejected on the
  record in ADR-0020.

## Capabilities

### New Capabilities

- `interaction-gated-sections`: detecting page sections withheld behind an
  in-page interaction, and reporting them as unretrieved rather than absent.

### Modified Capabilities

- `fetch-response`: adds the gated-section confidence cap alongside the existing
  cap requirements, and declares the meaning of `confidence` and of
  `operator_hints[].code` as the agent branching surface.

## Impact

- `src/a2web/hints.py` — one `HINT_CODES` member, one factory. A contract change,
  **not** an envelope-shape change (precedent: `query_title_mismatch`), so the
  `AGENTS.md` "Ask First" gate is not tripped.
- `src/a2web/fetcher/sufficiency/` — one new phase module, mirroring
  `_phase_listing_completeness`; must also be invoked from
  `fetcher/retrieval/escalate/seam.py`, with a symmetric clear so a future
  click-capable rung retracts the signal.
- `src/a2web/packages/llm_extract/prompts.py` — a gate-handle menu section and
  the corresponding router-schema field; prompt version bump.
- `src/a2web/fetcher_response.py` — the cap + hint emission, alongside
  `query_title_mismatch`.
- `src/a2web/models.py`, `src/a2web/routers.py` — docstring and tool-description
  declarations only.
- `eval/corpus.yaml` — the motivating case, phrased against stable structural
  facts.
- No wire-golden re-bless, no CLI-contract delta, no `_TSV_FIELDS` change, no
  `FetchContext` member beyond the phase's own typed field.

### Out of scope (tracked separately)

- A general `query_unanswered` flag — needs a producer census before its `false`
  means anything (ADR-0009 §46).
- `FetchStatus.partial` is declared on the wire contract and never produced.
- The ADR-0017 severity ladder has no rung for *verified AND must-act*.
- `hepsiburada.com` is absent from `_JS_HEAVY_HOSTS_SEED` while `trendyol.com`
  and `aliexpress.com` are present.
