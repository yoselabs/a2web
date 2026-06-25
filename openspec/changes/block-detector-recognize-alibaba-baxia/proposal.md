## Why

AliExpress (and every Alibaba-family site) fronts its content with the Baxia
"punish" anti-bot interstitial. The raw `curl_cffi` tier gets HTTP 200 with a
JS shell that extracts to **0 chars**, so `block_detector` returns a bare
`length_floor` (`subsystem=None`, no escalation) and the orchestrator **gives
up silently** — even though `aliexpress.com` is already in
`_JS_HEAVY_HOSTS_SEED`. Live PoCs this session confirmed: the gate never
escalates to the browser tier it was meant for, and the failure is mislabeled
as "thin content" rather than "blocked by anti-bot". This is best-effort scope:
make a2web *try* the browser tier on these pages and *fail honestly* when it
can't — no proxy work, no handler, no captcha-solving.

## What Changes

- Add an **Alibaba-Baxia detector branch** to `block_detector.evaluate(...)`,
  in the same shape as the existing `turnstile` / `akamai_bmp` / `anubis`
  branches: when the Baxia/"punish" fingerprint is present, emit
  `BlockResult(verdict=anti_bot, subsystem="alibaba_punish",
  escalation=EscalationSignal(next_tier="browser", reason="alibaba_punish"))`
  (`anti_bot` matches the sibling anti-bot branches and is an honest failure
  verdict when escalation is capped on an already-flagged IP).
- Fingerprint (proven in PoCs, high-confidence): URL path
  `/_____tmd_____/punish` with `x5secdata`/`x5step` query params; body text
  `"unusual traffic from your network"` / `"Please slide to verify"` /
  `"Captcha Interception"` / `"Пройдите проверку"`; HTML tokens `baxia` /
  `nocaptcha` / `slidecaptcha` / `_____tmd_____`.
- The branch fires on **any tier's** content, so a Baxia page returned by the
  *browser* tier (IP already flagged — PoC showed even real Chrome gets the
  slider) is detected too: a2web surfaces a distinct `alibaba_punish` subsystem
  in the decision log instead of a misleading thin-content verdict. Escalation
  stays bounded by the existing `browser_dispatches < 1` cap (no loop).
- **No false positives**: a thin page *without* the Baxia fingerprint still
  returns plain `length_floor` with `subsystem=None`, `escalation=None`.

Net effect — two honest outcomes: (1) clean IP → raw escalates to Camoufox,
which renders successfully; (2) flagged IP → fetch fails loudly with an
`alibaba_punish` fingerprint instead of silently.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `quality-gate`: add a requirement that the gate recognizes the Alibaba Baxia
  / "punish" anti-bot interstitial and emits a browser-escalation signal with a
  distinct `alibaba_punish` subsystem, while preserving today's behavior for
  non-Baxia thin pages.

## Impact

- **Code**: `src/a2web/packages/block_detector.py` (one new detector branch +
  marker constants). No change to `EscalationSignal`, the planner, or the
  browser tier — they already consume `next_tier="browser"`.
- **Tests**: gate unit tests asserting the Baxia fingerprint yields
  `next_tier="browser"` / `subsystem="alibaba_punish"`, and that a non-Baxia
  thin page is unchanged.
- **Behavior**: AliExpress and other Alibaba SPAs now escalate to the browser
  tier (best-effort); failures carry an honest fingerprint. No new deps, no
  wire/signature changes, no proxy or handler work.
- **Explicitly deferred to `BACKLOG.md` (NOT this change)**: browser tier
  ignoring `proxy_url` (`browser.py:135` — the keystone for real reliability),
  KZ residential proxy provisioning, per-IP pacing/rotation, an AliExpress
  SSR/XHR product-JSON handler, and the probabilistic-ceiling reality.
