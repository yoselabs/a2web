## Context

`record_extract` locates the dominant repeated record region of a page and
renders each record to markdown for the extractor. A record's text is assembled
by `detector._own_text` (`detector.py:87-99`):

```python
parts: list[str] = []
if el.text:
    parts.append(el.text)
for child in el:
    if isinstance(child.tag, str) and _signature(child) != record_sig:
        parts.append(_own_text(child, record_sig))   # recurse
    if child.tail:
        parts.append(child.tail)
return "".join(parts)        # ← distinct DOM text nodes fused with no separator
```

then `text = _collapse(_own_text(...))` where `_collapse = " ".join(text.split())`.

Two structures are destroyed at the `"".join`:

1. **Node boundaries.** Sibling spans with no intervening whitespace text node
   fuse: `<del>890 TL</del><span>%21</span><span>700 TL</span>` →
   `890 TL%21700 TL`. `_collapse` cannot help — there is nothing to collapse.
2. **Answer-bearing markup.** The `<del>` (struck-through list price) is
   flattened to bare text, so the extractor cannot tell the original price from
   the price the customer pays.

The frozen regression case `regression/hepsiburada-listing-price` is the
captured proof: the extractor answers with the list price (890) as the selling
price and fabricates a 1,700 list from the fused `%21700` digits, at
`confidence: high`. This is the `record_extract` instance of the ADR-0003
value-blind-projection class.

## Goals / Non-Goals

**Goals:**

- Make `record_extract`'s text projection structurally incapable of fusing
  distinct DOM text nodes.
- Preserve answer-bearing markup (strikethrough) across the boundary so
  list-vs-sale is recoverable by the extractor.
- A *general* fix: no site-specific, price-specific, or currency-specific
  special-casing anywhere (that is the symptom-patch ADR-0003 forbids).
- Deterministic, offline proof that the projection is fixed (not only a live
  judge): the fused token must be gone from the projected content.
- Confirm the `record_extract` half of ADR-0004; re-point its `json-extract`
  half to a future change.

**Non-Goals:**

- The `json-extract` typed schema.org boundary (ADR-0004's original framing) —
  same class, different site, no captured regression yet. Deferred.
- Any change to tool signatures or the response envelope.
- The value-blind *gate* (confidence rubber-stamping) — that is ADR-0006 /
  change `answerability-escalation`.

## Decisions

### D1 — Fix at assembly (`_own_text`), not at display (`render.py`)

Separate distinct text fragments with a single space when assembling
`_own_text`, so node boundaries survive into `Record.text` and everything
derived from it. `_collapse` already normalizes runs of whitespace, so adding
separators is safe and idempotent.

*Rejected:* inserting a delimiter in `render.py` for the price specifically.
That is field-specific and site-shaped — the symptom-patch ADR-0003 bans. The
fusion is born at assembly; fix it there, once, for every record on every site.

### D2 — Preserve strikethrough as markdown `~~...~~`

When an own-scope descendant is a strikethrough element (`<del>`, `<s>`,
`<strike>`), wrap its text in markdown strikethrough in the projected text:
`~~890 TL~~ %21 700 TL`. The extractor's input language *is* markdown, and
`~~...~~` carries exactly the semantics we need — "this value is no longer the
operative one" — so the model can distinguish a struck-through list price from
the live sale price without any price-aware logic in our code.

*Rejected:* a typed `Price`/`Offer` object on the DOM path. The DOM gives us
markup, not reliable semantic roles; a typed-price extractor here would be
guessing. The markdown-strikethrough convention is the minimal *structure-
preserving* signal and stays domain-agnostic. (Typed objects are the right tool
on the `json-extract` path, which is the deferred ADR-0004 half.)

### D3 — Deterministic projection assertion as the acceptance gate (BDD-first)

The fix is proven at two levels:

- **Deterministic (gates `make check`, offline):** replay the frozen raw bytes
  through the real projection and assert the *content* no longer fuses — the
  token `890 TL%21700` is absent and the struck list price is marked. This is
  computed from frozen bytes with no LLM, so it is a permanent, offline gate
  for the class-fix. Per BDD-first, this assertion is written **red** (it fails
  today, documenting the bug at the projection level) and the fix turns it
  green.
- **Judged (under `make bench` / `eval-refresh`, live):** `make eval-refresh
  CASE=regression/hepsiburada-listing-price` re-captures — new content → new
  live LLM call → new answer — and the blessed answer flips from the list price
  to the discounted price, matching `baseline/answer.md`.

Note the cassette interaction: the frozen LLM response is keyed per-case (MVP),
so after the projection changes, the *recorded* answer is stale. That is
expected and correct — `eval-refresh` re-records it. The deterministic gate
deliberately asserts the **projection** (content), not the stale frozen answer,
so `make check` proves the fix without a live call.

### D4 — Extend the replay contract with content assertions

Add `content_excludes` / `content_includes` keys to the replay contract matcher
(`tests/eval_replay/replay.py`) and surface `content_md` in `observe(...)`, so a
case can assert deterministic facts about the projected content. This is the
mechanism D3's deterministic gate uses.

## Risks / Trade-offs

- **[Adding separators changes every record's text, not just prices]** →
  Intended: it is a general projection fix. Mitigation: the existing
  record-extraction tests + the four-axis output benchmark guard against
  collateral regressions; spaces are idempotent under `_collapse`.
- **[`~~...~~` could appear in non-price struck content (e.g. edited forum
  posts)]** → That is correct behavior: struck text *is* semantically
  superseded; marking it helps the extractor everywhere, not just on prices.
- **[Token cost rises slightly (more structure reaches the extractor)]** →
  Bounded and measured by the eval substrate; the fidelity gain is the point
  (ADR-0002: volume is never a fidelity proxy).
- **[Strikethrough detected by tag only, missing CSS `line-through`]** → lxml
  gives us tags reliably; CSS-styled strikethrough without a semantic tag is
  out of reach here and is the kind of case the rendered-surface grounding
  change (ADR-0007) addresses. Documented, not silently dropped.

## Migration Plan

1. Add the deterministic projection assertion to the regression case (red).
2. Fix `_own_text` node separation → the fusion token disappears.
3. Add strikethrough preservation → list price marked.
4. Add the arch fitness function (ban no-separator descendant-flatten).
5. `make eval-refresh` (live) → re-bless inputs + the discounted judged answer.
6. `make check` green; reconfirm ADR-0004 (record_extract half).

No rollback complexity: pure projection change behind the extractor, no schema
or signature change. Revertable by reverting the commit.

## Open Questions

- Should the separator be a space or a stronger delimiter (e.g. ` · `)? Start
  with a space (least surprising, idempotent under `_collapse`); revisit only
  if the judge shows the model still mis-segments.
- Does strikethrough alone flip the judged answer, or is the node-separation
  enough on its own? The eval substrate answers this empirically during apply —
  implement separation first, refresh, and see if the judge already flips
  before adding markup complexity.
