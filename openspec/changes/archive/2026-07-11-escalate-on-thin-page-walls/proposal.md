## Why

A server that answers a scraper with an **essentially empty HTML document** — `<html><body></body></html>`, a bare shell with no visible text — is emitting one of the oldest silent-block signals there is: a WAF that would rather serve *nothing* than a 403. Today a2web trusts it. The content gate (`block_detector`) keys its thin-page branch on the **extracted** `content_md` length, and a near-empty raw body with no recognizable anti-bot fingerprint falls through to a bare `BlockVerdict.length_floor` with **no escalation** (`block_detector.py:237`) — a deliberate "preserve today's behavior" terminal (`quality-gate` spec). So a blank page is reported as a (low-value) success or a soft miss, without the browser **or** the paid scraper ever being tried.

That is the same class of gap `escalate-on-status-derived-walls` (Step 2) closed for transport verdicts: a blank 2xx is circumstantial evidence of a silent block, so it belongs in the escalate-not-terminal bucket alongside a 403 — a latent ADR-0009 violation (*never tolerate an unfetched URL*). The distinction from the thin-content carve-outs is deliberate and load-bearing: **this is about the raw HTML being genuinely empty, not about a fully-rendered page that merely extracts sparse.** Truly-empty raw bodies are rare, which is exactly why one is a strong signal worth spending an escalation on.

## What Changes

- **New gate detection: near-empty raw HTML → `BlockVerdict.blank_page` with browser escalation.** Keyed on the **raw body's visible text** (tags + whitespace stripped) falling below a small `BLANK_HTML_THRESHOLD`, distinct from the `content_md` `LENGTH_FLOOR`. Checked *after* all existing anti-bot markers and *after* the JS-shell (`js_required`) branch, so a shell that a known fingerprint already claims is unaffected; this catches the marker-less bare-empty document that is terminal today.
- **New verdict `blank_page`** (package `BlockVerdict.blank_page` + domain `Verdict.blank_page`), closed-enum, ranked in the verdict projection. It is a *wall* verdict for escalation purposes but carries its own honest terminal + hint.
- **Full ladder before conceding:** a `blank_page` escalates to the self-hosted browser first (a JS-rendered page can fill an empty shell); if the render is still blank, it escalates to the **paid web-scraper** tier (residential + real browser — the strongest attempt) via the existing `paid_last_resort` rung. Both dispatches stay under their existing caps (browser ≤ 2, paid ≤ 1).
- **New terminal failure condition: surviving `blank_page`.** When the browser **and** paid scraper both return an essentially empty body, the fetch ends `status: failed` + `retrieval_incomplete: true` with the critical **`try_user_browser`** hint, exactly as the other wall verdicts. *(Revised during live sanity: originally emitted a distinct `blank_page` hint on the theory a blank source isn't browser-passable; g2.com disproved it — a near-empty body is usually a silent anti-bot block that a real browser passes, and the two are indistinguishable, so the safe default is `try_user_browser`. The `blank_page` verdict is kept for diagnostics only.)*
- **Intended behavior change:** a marker-less near-empty raw page that today ends as a bare `length_floor` (soft, no escalation) will now spend one browser and one paid attempt, then fall to the new loud `blank_page` terminal if still empty. Existing `quality-gate` scenarios that assert "no-marker thin page → no browser escalation" are **unaffected**, because they operate on pages with substantial raw HTML that merely extracts thin — a different population from near-empty raw. Any test that happens to feed a near-empty raw body expecting bare `length_floor` is a legitimate expectation change.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities

- `quality-gate`: a new `blank_page` detector branch keyed on near-empty **raw HTML** visible text, emitting `BlockVerdict.blank_page` + `EscalationSignal(next_tier="browser", reason="blank_page")`. The existing extracted-thin `length_floor` behavior (for pages with real raw HTML) is unchanged — the two populations are disjoint.
- `cascade-decision-log`: `blank_page` joins the escalation ladder as a wall verdict — the existing gate-browser rule dispatches the browser, and `paid_last_resort` carries a still-blank result to the paid scraper. A `blank_page` that survives the full ladder is terminal.
- `retrieval-completeness`: the never-silently-miss floor covers a surviving `blank_page` — `status: failed` + `retrieval_incomplete` + the critical `try_user_browser` hint (a surviving blank body is treated as a likely silent anti-bot wall, not a genuinely empty resource).

## Impact

- `src/a2web/packages/block_detector.py` — new `BlockVerdict.blank_page`; a visible-text-emptiness check on `raw_html` with a `BLANK_HTML_THRESHOLD`, inserted after the marker/JS-shell branches and before the bare `length_floor` fallthrough; returns `escalation=EscalationSignal(next_tier="browser", reason="blank_page")`.
- `src/a2web/models.py` + `src/a2web/decision_log.py` — add `Verdict.blank_page`; rank it in `_verdict_rank` as a wall-class terminal (alongside `block_page_detected` / `anti_bot`).
- `src/a2web/fetcher.py` — add `blank_page` to `_WALL_VERDICTS` so the paid last-resort + loud-terminal path AND the shared `try_user_browser` hint run for it. Confirm the browser→paid ordering holds for it.
- `src/a2web/actions/playbook.py` — verify `paid_last_resort` and the gate-browser rule both fire for `blank_page` (it should ride existing rules as a wall verdict; add a targeted rule only if the wall-verdict set does not already cover it).
- **Cost:** each near-empty raw page now spends up to one browser + one paid scraper request. Bounded per-fetch by the existing caps; the aggregate cost is the live open question (paid egress is metered). Recorded in design Open Questions — decision for now is to spend the attempt, since truly-empty raw bodies are rare.
- No wire/envelope shape change beyond the new `blank_page` verdict value + hint code; no tool-signature change; no new dependency.

Not in scope: extracted-thin `length_floor` behavior for substantial-HTML pages (unchanged); the transport-verdict escalation (Step 2, shipped); the content-wall body-bearing `try_user_browser` gap found during Step 2's live sanity (separate follow-up); `single-source-escalation-policy` (Finding 2, separate).
