## ADDED Requirements

### Requirement: Near-empty raw HTML is detected as a blank_page and escalated

The content gate SHALL detect a response whose **raw body carries near-zero visible text** as a distinct `BlockVerdict.blank_page`, separate from the extracted-thin `length_floor` verdict. Visible text SHALL be computed from `raw_html` by stripping tags and collapsing whitespace; the branch SHALL fire when that visible text length is below a small `BLANK_HTML_THRESHOLD` (near-zero — sized so a bare/empty document matches but a short-but-present stub page, e.g. a ~480-char "JavaScript is disabled" notice, does not).

The `blank_page` check SHALL run **after** all anti-bot marker branches (turnstile, akamai_bmp, anubis, alibaba_punish, cf_iuam, search-captcha) and **after** the `js_required` JS-shell branch, and **before** the bare `length_floor` fallthrough. A body a marker or the JS-shell branch already claims keeps that specific verdict; only a marker-less near-empty body becomes `blank_page`.

A `blank_page` result SHALL carry `escalation = EscalationSignal(next_tier="browser", reason="blank_page")` so the orchestrator escalates to the browser tier (a JS-rendered page can fill an empty shell) rather than returning the empty body.

This detection keys on the **raw HTML** being empty, NOT on a fully-rendered page extracting sparse content. Pages with substantial raw HTML that merely extract thin SHALL continue to return `length_floor` per the existing thin-content behavior — the two populations are disjoint and that behavior is unchanged.

#### Scenario: An empty document escalates to browser

- **WHEN** the gate evaluates an HTTP 200 `text/html` response whose raw body is `<html><head></head><body></body></html>` (visible text below `BLANK_HTML_THRESHOLD`) with no anti-bot marker
- **THEN** `verdict == BlockVerdict.blank_page` and `escalation == EscalationSignal(next_tier="browser", reason="blank_page")`

#### Scenario: A short-but-present stub is NOT blank_page

- **WHEN** the gate evaluates a ~480-char body carrying visible text (e.g. "JavaScript is disabled...") with no marker
- **THEN** `verdict != BlockVerdict.blank_page` (it remains `length_floor` per existing behavior — the raw body has real visible text)

#### Scenario: A substantial page that extracts thin stays length_floor

- **WHEN** the gate evaluates a page with substantial raw HTML whose extracted `content_md` is below `LENGTH_FLOOR`, and the raw visible text is above `BLANK_HTML_THRESHOLD`, with no marker
- **THEN** `verdict == BlockVerdict.length_floor` with no `blank_page` escalation (existing thin-content behavior is unchanged)

#### Scenario: A fingerprinted empty shell keeps its specific verdict

- **WHEN** the gate evaluates a near-empty body that ALSO matches a JS-shell marker (`js_required`) or an anti-bot fingerprint
- **THEN** the specific marker branch wins (`length_floor`+`js_required` or the `anti_bot` fingerprint), NOT `blank_page` (the `blank_page` branch is the marker-less fallthrough)
