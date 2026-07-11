## 1. Gate: length-independent anti-bot exemption

- [x] 1.1 ~~Add `structured_answer` parameter to `block_detector.evaluate()`~~ — **implementation-site correction**: the domain-level `evaluate()` *wrapper* in `src/a2web/fetcher.py:123-184` (not the pure package function) already accepts `structured_answer: bool` and already does the analogous bare-`length_floor` promotion post-processing after calling `_package_evaluate`. That's the correct existing seam for a domain-level exemption (tach.toml keeps `packages/` free of `a2web.<domain>` imports, so this belongs here, not in `block_detector.py`) — no change needed to `block_detector.py` at all.
- [x] 1.2 Added the `akamai_bmp`/`turnstile` exemption branch in `fetcher.py`'s `evaluate()` wrapper (after the existing bare-`length_floor` promotion, ~line 184): promotes `Verdict.anti_bot` → `Verdict.ok` (clears subsystem + escalation, sets `promoted_structured=True`) when `structured_answer` is `True`, `subsystem in ("akamai_bmp", "turnstile")`, and `len(content_md) >= LENGTH_FLOOR`.
- [x] 1.3 Same branch covers both markers (single `subsystem in (...)` check) — no separate turnstile branch needed.
- [x] 1.4 Confirmed untouched: the new branch's condition is scoped to `subsystem in ("akamai_bmp", "turnstile")` only; `anubis`/`alibaba_punish`/`cf_iuam`/`search_captcha`/generic `block_page_detected` verdicts never reach this branch (verdict wouldn't be `Verdict.anti_bot` with a matching subsystem for those).
- [x] 1.5 Call site already passes `structured_answer=any(c.answer_bearing for c in fc.content_candidates)` at `fetcher.py:1636` (pre-existing, for the bare-`length_floor` promotion) — no change needed, the same value now also feeds the new branch.
- [x] 1.6 Traced: `_phase_gate_and_escalate` records the gate outcome via `fc.observe(verdict=gate_result.verdict, escalation=gate_result.escalation, subsystem=gate_result.subsystem)` (`fetcher.py:1657-1663`), which is the sole input to `decide_next`/the planner loop. Nothing else in `fetcher.py` or `actions/` special-cases the `akamai_bmp`/`turnstile` subsystem strings (confirmed via grep) — the branch clearing verdict/subsystem/escalation to the same shape as the existing bare-`length_floor` promotion is sufficient; no separate planner change needed.

## 2. Display pick — DROPPED FROM THIS CHANGE

- [x] 2.1 ~~Make `_pick_display_candidate`'s `answer_bearing` short-circuit length-independent.~~ **Attempted, reverted, and dropped from scope** (user decision after `make check` regression — see design.md postscript). `Article`/`NewsArticle` are `_PREFERRED_LD_TYPES` in the shelf `json_in_html` package, so routine SEO `Article` JSON-LD makes ordinary blog/news pages `answer_bearing = True` too — an unconditional "answer_bearing always wins" rule silently replaced real article prose with a metadata stub (`test_blog_fixture_yields_real_envelope` caught this). A pre-existing test (`test_above_floor_prose_keeps_display_over_structured`) independently confirmed this was deliberate prior behavior. Reverted `_pick_display_candidate` to its original form; removed the dependent test. Deferred to `BACKLOG.md` for a future change with its own design pass (see design.md postscript for the two candidate approaches: `@type`-level split, or a prose-quality signal via trafilatura's `score`).
- [x] 2.2 N/A — dropped with 2.1.

## 3. Tests

- [x] 3.1 Added cases to `tests/capabilities/quality_gate/test_gate.py` (the actual home of `fetcher.evaluate`'s `structured_answer` tests — not `tests/packages/test_gate.py`, which tests the pure `block_detector.evaluate` and doesn't have a `structured_answer` param): `akamai_bmp` + above-floor + `structured_answer=True` → `ok`; `turnstile` + above-floor + `structured_answer=True` → `ok`; `akamai_bmp` + above-floor + `structured_answer=False` → unchanged `anti_bot`; `akamai_bmp` + below-floor + `structured_answer=True` → still `anti_bot`.
- [x] 3.2 Confirmed: `tests/packages/test_gate.py`'s `test_akamai_bmp_marker_suggests_browser`, `test_turnstile_marker_suggests_browser`, `test_anubis_marker_with_short_content` untouched (they test the package function, not the wrapper this change modified) — all pass.
- [x] 3.3 Dropped with Task 2.
- [x] 3.4 Confirmed: `test_flat_catalog_replaces_on_length` and `test_good_article_not_clobbered_by_record_cluster` (this file's versions of "prose-preferred, not longest" / "article never clobbered") pass unmodified — the latter also served as the regression guard that caught the Task 2 issue.
- [x] 3.5 Dropped with Task 2.

## 4. Verification

- [x] 4.1 `make check` passed: lint clean, `ty` clean, `999 passed, 2 deselected` at 89.93% coverage (≥85% required) — scope is the Task 1 gate fix only.
- [x] 4.2 Re-ran the live Koçtaş probe (`mcp__a2web__fetch_raw` and `mcp__a2web__ask`, `debug=true`) against the product URL from the 2026-07-09 explore session, using the locally-modified source (not yet reinstalled globally — see note). Confirmed the gate fix works as designed on the exact live incident.
- [x] 4.3 `make bench` deferred — this change is now a narrow, purely-internal gate/escalation fix with no effect on answer content or extraction quality (the display-pick change that would have moved output quality/cost was dropped). Bench-worthiness criteria target changes that could move answer quality or cost; this one only removes a redundant escalation step, already directly verified live in 4.2.

## 5. Housekeeping

- [x] 5.1 Updated `BACKLOG.md`: marked the gate item shipped, added a fresh deferred entry for the display-pick idea (with the concrete regression finding), so a future session doesn't have to rediscover it from scratch.
