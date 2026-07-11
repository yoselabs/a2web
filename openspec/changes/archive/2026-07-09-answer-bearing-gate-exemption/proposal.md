## Why

A 2026-07-09 live re-probe of a real Koçtaş product page (`BACKLOG.md` §"2026-07-09 — Koçtaş re-probe: it wasn't a wall") found a2web paying an unnecessary browser-escalation tax on a page whose answer was already fully present in a strong JSON-LD `Product` payload. Diagnostics: the raw `curl_cffi` tier returned a clean `200` in ~500ms carrying a JSON-LD `offers` block (`price=4221.97 TRY, availability=InStock`) already classified `answer_bearing=True` by the existing `json-extract` predicate — yet the gate forced a browser-tier escalation anyway (an `akamai_bmp` marker match, length-independent), adding 3-9s and downgrading `confidence` to `medium` for an answer that didn't change.

This traces back to a signal a2web already computes (`ContentCandidate.answer_bearing`, `json_in_html.is_answer_bearing` — a strict, hard-to-cheaply-spoof predicate requiring a preferred schema.org `@type` with ≥3 populated fields) but does not fully consult at this decision point. This is cheaper and safer to fix now than the originally-suspected "unbeatable DataDome wall" framing from the 2026-07-07 backlog entry, which this session's re-probe superseded — no cookie plumbing, no envelope change.

**Scope note:** the same re-probe also found `fetch_raw`'s display pick surfacing the wrong `content_md` on this page (boilerplate prose beating the shorter, correct structured candidate). An implementation attempt at fixing that in this change was reverted after `make check` showed it regressing ordinary articles — see "Deferred" below. This change now covers the gate fix only.

## What Changes

- Add a narrow gate exemption: when `evaluate()`'s length-independent anti-bot markers (`akamai_bmp`, `turnstile` — NOT `anubis`, `cf_iuam`, or generic `block_page_detected`, which stay untouched) match on a response whose extracted content is **above `LENGTH_FLOOR`** and which carries an `answer_bearing=True` structured candidate, the forced browser escalation SHALL be skipped and the verdict promoted to `ok`. This is a **new, narrowly-scoped branch** distinct from the existing "bare `length_floor` + `structured_answer`" promotion (`quality-gate` capability) — it must not weaken the existing, deliberately-tested "anti-bot verdict is NOT masked by an embedded [stub] payload" behavior for genuinely thin/challenge-shell responses.
- Add fixtures/tests covering: an `akamai_bmp`/`turnstile` marker with above-floor content + strong answer-bearing JSON-LD (new `ok` outcome); the existing thin/stub anti-bot scenarios continuing to escalate unchanged.
- Correct the framing in `BACKLOG.md`'s superseded 2026-07-07 entries (already done this session) — no further action needed there.

No tool signature, envelope/wire shape, or dependency changes. `confidence` still reports `medium`/`high` per existing rules — this change affects which verdict/escalation path is taken, not the response schema.

### Deferred (not in this change)

The `fetch_raw` display-pick fix (`_pick_display_candidate` surfacing an `answer_bearing` candidate over above-floor prose) is deferred to `BACKLOG.md`. An unconditional "`answer_bearing` beats prose" rule was implemented and reverted during this change's apply phase: `Article`/`NewsArticle` are preferred schema.org types too (`json_in_html._PREFERRED_LD_TYPES`), so any ordinarily SEO'd blog/news page's routine `Article` JSON-LD (headline/author/date) is `answer_bearing=True` — the rule silently replaced real, substantial article prose with that metadata stub (`tests/capabilities/tier_pipeline/test_fetcher.py::test_blog_fixture_yields_real_envelope` caught this). A pre-existing test, `tests/capabilities/quality_gate/test_structured_answer_exemption.py::test_above_floor_prose_keeps_display_over_structured`, independently encodes the same guarantee (an embedded `Product` schema must not hijack a genuine article's prose) — confirming this was deliberate prior behavior, not an oversight. `answer_bearing` measures structured-payload strength, not prose relevance/quality, so it's the wrong signal to gate this on alone. Needs its own design pass (e.g. restricting to non-editorial `@type`s, or a prose-quality signal such as trafilatura's extraction confidence score) before a future attempt.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `quality-gate`: new requirement — length-independent anti-bot markers (`akamai_bmp`, `turnstile`) exempt from forcing browser escalation when content is above `LENGTH_FLOOR` and an `answer_bearing` structured candidate is present; verdict promotes to `ok`. Existing "bare `length_floor`" promotion requirement and its thin/stub anti-bot non-masking scenarios are unchanged.

## Impact

- `src/a2web/fetcher.py` — the domain-level `evaluate()` wrapper (`~123-190`, not the pure `packages/block_detector.py` function), adding the new exemption branch after the existing bare-`length_floor` promotion. Call site (`_phase_gate_and_escalate`, `~1620-1636`) required no change — it already computed and passed `structured_answer`.
- `tests/capabilities/quality_gate/test_gate.py` — new cases alongside the existing `structured_answer` exemption tests.
- `openspec/specs/quality-gate/spec.md` — delta spec.
- `BACKLOG.md` — already corrected this session for the gate finding; the display-pick idea is re-recorded there as a fresh deferral (see "Deferred" above) once this change is applied.
