## Context

`ask(url, question)` on a thin-but-structured page (e.g. a company contact
page) fails today even when the page's JSON-LD carries the exact answer. Traced
end-to-end on `veito.com/iletisim-EN.html`:

```
_phase_extract:
  trafilatura → thin/near-empty prose
  _escalate_via_json → renders the LocalBusiness JSON-LD into a json_synth
      ContentCandidate (telephone "444 3 061", email "destek@veito.com")  ← answer is here
  _pick_display_candidate → content_md ≈ sub-floor prose (or the json rows)
_phase_gate_and_escalate:
  evaluate(content_md) → len < LENGTH_FLOOR(500), no SPA markers
      → BARE Verdict.length_floor (subsystem=None, escalation=None)
  planner: no browser signal, not paid-worthy → terminal
  → status=failed
_phase_extract_answer:
  guard `verdict != ok` → RETURN (extraction skipped)
  → answer=null
```

Two facts make the fix small:

1. `json_to_markdown_rows` already renders single-entity JSON-LD by
   **default-keep** (`extraction` spec, "single-entity JSON-LD rendering is
   default-keep"), so LocalBusiness/Organization already render their
   answer-bearing scalars. Nothing new is needed to *render* the answer.
2. `_phase_extract_answer` already feeds the LLM the **whole candidate menu**
   (`menu = assemble_menu(fc.content_candidates)`), not just the display
   `content_md`. So once extraction runs, Haiku sees the json_synth rows.

The only blocker is the gate verdict. The architecture already has the precedent
for "small-but-complete is not a truncated shell" — the `is_json` promotion at
the `evaluate(...)` seam (`if is_json and verdict is length_floor: verdict =
ok`). This change applies the same wisdom to structured-data-backed content.

## Goals / Non-Goals

**Goals:**
- A thin page whose answer is in answer-bearing structured data resolves to
  `ok` and answers, instead of `failed/null`.
- `fetch_raw` (no LLM) on such a page surfaces the structured answer in
  `content_md`, not a thin nav/footer fragment.
- Contact/org/event schemas are treated as first-class answer sources
  alongside commerce/editorial.
- Zero envelope-shape / tool-signature / dependency changes.

**Non-Goals:**
- Making `record_synth` (listing) candidates trigger the exemption — listing
  completeness owns the "is this listing truncated?" question; folding it in
  here would risk regressing the SPA-listing escalation path.
- Changing confidence scoring. A promoted page follows the normal `ok` path;
  the extractor assesses confidence from the data.
- New tiers, planner rules, or escalation types.
- Recognizing structured data the renderer can't already surface (RDFa stays
  out of scope per json-extract D1).

## Decisions

### D1: Exempt at the fetcher `evaluate(...)` seam, keyed on the candidate menu — not inside the block detector

The block detector (`packages/block_detector.py`) is policy-free and content-md
only; it has no access to `fc.content_candidates` and must not gain domain
schema knowledge. The `is_json` exemption already lives in the **fetcher seam**
`evaluate(...)` (`fetcher.py:116`), post-processing the package verdict. We add a
sibling `structured_answer: bool` parameter and mirror the block:

```python
if structured_answer and verdict is Verdict.length_floor:
    verdict = Verdict.ok
    subsystem = None
```

`_phase_gate_and_escalate` computes the flag as
`any(c.answer_bearing for c in fc.content_candidates)` and passes it in.

*Alternative considered:* apply the promotion in `_phase_gate_and_escalate`
after `evaluate()` returns, outside the seam. Rejected — it splits the
"small-but-complete promotion" logic across two sites; keeping it beside
`is_json` in `evaluate()` is one home, one pattern.

### D2: `ContentCandidate.answer_bearing: bool` — a typed field, set by the ladder

Rather than re-deriving schema strength at the gate, the `json_synth` rung tags
each candidate at creation from the package predicate:

```python
candidates.append(ContentCandidate(
    source="json_synth",
    content_md=rendered,
    answer_bearing=is_answer_bearing(payload),
))
```

`ContentCandidate` is a `dataclass(slots=True, frozen=True)`; adding one typed
`bool` respects the no-`dict[str,Any]`-bag invariant. `trafilatura` and
`record_synth` candidates default `answer_bearing=False` (prose is subject to
the normal floor; records are out of scope per Non-Goals).

*Alternative considered:* have the gate call `is_answer_bearing` on re-parsed
payloads. Rejected — double parse, and it drags schema policy into the gate
seam.

### D3: `is_answer_bearing(payload)` = the existing "strong" predicate, widened

The package already has `_ld_json_strong` / `_microdata_strong` (strong =
preferred `@type` with ≥3 populated fields), used by `rank_payloads` bucketing.
We (a) widen `_PREFERRED_LD_TYPES` and the microdata strong set to add
`LocalBusiness`, `Organization`, `ContactPoint`, `Event`, `Recipe`, and
(b) expose a public `is_answer_bearing(payload) -> bool` that returns True for a
strong ld_json or strong microdata payload. This keeps the exemption honest: a
100-char `LocalBusiness` with only `name`+`url` (2 fields) stays *weak* and does
**not** trigger promotion; Veito's 5-field LocalBusiness does.

The `≥3 populated fields` threshold is unchanged — junk payloads still rank
weak, so the exemption cannot mask an empty SPA shell that happens to carry a
stub OG/ld_json.

### D4: Display pick prefers answer-bearing structured over sub-floor prose

`_pick_display_candidate` currently prefers prose for display. When the picked
prose is below `LENGTH_FLOOR` and an answer-bearing structured candidate exists,
the structured candidate wins the display slot. This is what makes `fetch_raw`
(which returns only `content_md`, not the menu) carry the answer. Above-floor
prose is unaffected — a normal article still displays its prose.

### D5: Scope the promotion to *bare* `length_floor` only

The mirror block fires only when `verdict is Verdict.length_floor` **and**
subsystem is the bare case (it runs after the `js_required` / `thin_browser` /
jina / anti-bot branches have set their subsystems, and only rewrites the bare
`length_floor`). A `js_required` SPA shell that also embeds a stub ld_json still
escalates to browser — we never let a strong-enough-looking payload short-circuit
a genuine wall. In practice a real answer-bearing schema on an SPA shell means
the page *did* server-render its answer, so promoting is correct even then;
scoping to the bare case is the conservative floor.

## Risks / Trade-offs

- **[False promotion: a stub schema masks a real failure]** → Mitigated by the
  unchanged `≥3 populated fields` strong threshold and by scoping to bare
  `length_floor` (D5). An empty SPA shell has no strong answer-bearing payload;
  a block/anti-bot page carries its own non-`length_floor` verdict.
- **[A promoted thin page enters cache]** → Acceptable: it is a legitimate
  answer-bearing page, not a block page. The block-page cache prohibition is
  keyed on wall verdicts, which this is not.
- **[Widening strong types shifts `rank_payloads` ordering on commerce pages]** →
  The new types are disjoint from existing ones; a page with both a `Product`
  and a `LocalBusiness` (e.g. a store page) now ranks both strong, ordered by
  `byte_size`. This is a strict improvement (more answer-bearing data in the
  menu), and the display pick is quality- not length-blind.
- **[`fetch_raw` display change surprises a parser relying on prose]** →
  `content_md` is already documented as a quality pick, not a stable prose dump;
  the change only triggers when prose was sub-floor (i.e. previously near-useless).

## Migration Plan

Pure additive behavior; no data migration. Ships in a normal version bump +
`make install-global`. Rollback = revert the change; no persisted state depends
on it. The four-axis output benchmark (`make bench`) should be run post-merge
since this moves output quality on the structured-page class; add a contact-page
case to the eval corpus.

## Open Questions

- Should `ContactPoint` nested inside `Organization`/`LocalBusiness` (rather than
  top-level) also count toward the strong field threshold? (Leaning yes — it's
  where phone/email often live — but the default-keep renderer already surfaces
  a shallow `contactPoint` dict, so the fields render regardless; the only
  question is whether they count toward `≥3` for the *strength* verdict.)
