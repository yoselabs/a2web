## ADDED Requirements

### Requirement: Alibaba Baxia "punish" interstitial recognized and escalated to browser

The quality gate SHALL recognize Alibaba's Baxia anti-bot "punish"
interstitial (the wall fronting AliExpress and other Alibaba-family sites) and
emit a browser-escalation signal with a distinct fingerprint, so the
orchestrator escalates to the browser tier instead of returning a bare
`length_floor`.

When `block_detector.evaluate(...)` sees a response whose `raw_html` matches the
Baxia fingerprint, the gate SHALL return
`BlockResult(verdict = BlockVerdict.anti_bot, subsystem = "alibaba_punish",
escalation = EscalationSignal(next_tier = "browser", reason = "alibaba_punish"))`.
`anti_bot` (not `length_floor`) is used to stay consistent with the sibling
anti-bot branches (`turnstile` / `akamai_bmp` / `anubis`) and to give an honest
failure verdict when escalation is capped on an already-flagged IP. The punish
page's `raw_html` carries the markers (the `_____tmd_____` path token,
`x5secdata`/`x5step` params, and the localized interstitial text), so no
final-URL parameter is threaded into the detector.

The Baxia fingerprint matches when ANY of the following hold:

- the final URL path contains `/_____tmd_____/punish`, OR carries an
  `x5secdata` or `x5step` query parameter;
- the response body contains any of the phrases `unusual traffic from your
  network`, `Please slide to verify`, `Captcha Interception`, or `Пройдите
  проверку`;
- the response HTML contains any of the tokens `_____tmd_____`, `baxia`,
  `nocaptcha`, or `slidecaptcha`.

Unlike the JS-shell rule, this branch SHALL fire on the marker alone,
independent of extracted content length, so a punish page surfaced by the
browser tier (when the egress IP is already flagged) is detected as well. The
branch SHALL be evaluated alongside the existing anti-bot branches
(`turnstile` / `akamai_bmp` / `anubis`), before the generic JS-shell and the
bare-`length_floor` fallthrough. Escalation remains bounded by the orchestrator's
existing `browser_dispatches < 1` cap; no new escalation type or planner rule is
introduced.

This requirement SHALL NOT change behavior for responses that do not match the
Baxia fingerprint: a thin page without the fingerprint SHALL continue to return
`BlockResult(verdict = BlockVerdict.length_floor)` with `subsystem` and
`escalation` unset, exactly as today.

#### Scenario: AliExpress Baxia punish URL escalates to browser

- **WHEN** the raw tier returns HTTP 200 whose final URL is
  `https://www.aliexpress.com//wholesale/_____tmd_____/punish?x5secdata=...&x5step=1`
  and trafilatura extracts 0 chars
- **THEN** `BlockResult.verdict == BlockVerdict.anti_bot`,
  `subsystem == "alibaba_punish"`, and
  `escalation == EscalationSignal(next_tier="browser", reason="alibaba_punish")`

#### Scenario: Baxia body phrase is recognized regardless of length

- **WHEN** any tier returns a body containing `Sorry, we have detected unusual
  traffic from your network. Please slide to verify` (a short interstitial well
  under the length floor) with no `/_____tmd_____/` in the URL
- **THEN** `subsystem == "alibaba_punish"` and
  `escalation.next_tier == "browser"`

#### Scenario: Russian-locale punish interstitial is recognized

- **WHEN** the browser tier returns the `aliexpress.ru` punish page whose body
  contains `Пройдите проверку` and HTML contains the `_____tmd_____` token
- **THEN** `subsystem == "alibaba_punish"` and `escalation.next_tier ==
  "browser"` (the browser_dispatches cap then prevents further escalation, and
  the fetch fails with the `alibaba_punish` fingerprint visible in the decision
  log)

#### Scenario: Thin non-Baxia page preserves existing behavior

- **WHEN** a tier returns a 300-char body that mentions the word `captcha` in
  prose but carries none of the Baxia URL tokens, phrases, or HTML markers
- **THEN** `BlockResult.verdict == BlockVerdict.length_floor`, `subsystem is
  None`, and `escalation is None` (no false-positive escalation)
