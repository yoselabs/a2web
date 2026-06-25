## Context

`block_detector.evaluate(...)` (`src/a2web/packages/block_detector.py`) is the
quality gate. It already has typed detector branches for `turnstile`,
`akamai_bmp`, `anubis`, generic JS-shell roots (`js_required`), and Cloudflare
IUAM (`cf_iuam` → `tls_impersonate`). Each sub-floor branch returns a
`BlockResult` carrying an `EscalationSignal(next_tier=..., reason=...)`; a
final fallthrough returns bare `length_floor` with no escalation.

Live PoCs this session established the AliExpress failure mode precisely:

- Raw `curl_cffi` → HTTP 200, a JS/Baxia shell, trafilatura extracts **0
  chars** → the bare-`length_floor` fallthrough fires (`subsystem=None`,
  `escalation=None`) → orchestrator stops. AliExpress is in
  `_JS_HEAVY_HOSTS_SEED`, but that seed only governs *post-browser* thin
  downgrades, so it does not help here.
- The block is Alibaba's **Baxia** anti-bot: a `/_____tmd_____/punish`
  interstitial ("unusual traffic from your network… please slide to verify").
  It is driven by **per-IP behavioral reputation**, not fingerprint — even a
  real Chrome on a real residential IP hits the slider once the IP is flagged.

## Goals / Non-Goals

**Goals:**
- Recognize the Baxia/"punish" fingerprint and escalate `raw → browser` (one
  new detector branch, same shape as `turnstile`/`anubis`).
- Make the failure *honest*: a distinct `alibaba_punish` subsystem in the
  decision log, including when the browser tier itself returns the punish page.
- Zero false positives on legitimate thin pages.

**Non-Goals (deferred to `BACKLOG.md`):**
- Browser tier honoring `proxy_url` (`browser.py:135` drops it) — the keystone
  for *reliable* access; without it Camoufox always exits the raw host IP.
- KZ residential proxy provisioning, per-IP pacing/rotation, an AliExpress
  product-JSON handler.
- CAPTCHA-solving — off-limits, never in scope.
- Any claim of *reliable* AliExpress access. This change is best-effort only.

## Decisions

**D1 — New ADDED requirement on `quality-gate`, not MODIFIED.** This adds a new
detector concern without altering any existing branch's behavior, so it is an
ADDED requirement. The three-condition JS-shell rule and the bare-`length_floor`
fallthrough are untouched.

**D2 — Match the most specific Baxia markers; avoid generic tokens.** Use the
proven, distinctive signals — URL `/_____tmd_____/punish` + `x5secdata`/`x5step`;
body phrases "unusual traffic from your network" / "Please slide to verify" /
"Captcha Interception" / "Пройдите проверку"; HTML `baxia` / `nocaptcha` /
`slidecaptcha` / `_____tmd_____`. The `_____tmd_____` token and the `x5secdata`
param are essentially unique to Alibaba's punish flow. *Rejected:* matching on
`window.goldlog` or a tiny body alone — too generic, would false-positive on
benign Alibaba pages and other small pages.

**D3 — Branch is gated on the marker, not on length.** Unlike the JS-shell rule
(which requires `len(content_md) < LENGTH_FLOOR`), the punish interstitial is
itself short but the marker is the authoritative signal. The branch fires when
the Baxia fingerprint matches regardless of extracted length, so it also
catches a punish page surfaced by the *browser* tier. Ordering: place the Baxia
branch alongside the other anti-bot branches (turnstile/akamai/anubis), before
the generic JS-shell and bare-`length_floor` fallthroughs.

**D4 — Reuse `EscalationSignal(next_tier="browser", reason="alibaba_punish")`.**
No new escalation type, no planner change — the existing
`_decide_gate_browser_signal` planner rule already escalates any gate signal
with `next_tier == "browser"` and `verdict is not ok`, capped at
`browser_dispatches < 1`. So loop-safety and browser dispatch are free.

**D5 — Operator hint is optional and out of the gate.** The honest-failure
value is delivered by the distinct `subsystem="alibaba_punish"` already visible
in diagnostics. A human-facing `OperatorHint` ("blocked by IP-reputation
anti-bot; retry from a clean residential IP / configure proxies") MAY be mapped
from that subsystem at the response-building layer, but is not required for this
change and adds no new gate behavior.

## Risks / Trade-offs

- **[Escalation succeeds but browser tier ALSO gets punished]** → Expected and
  acceptable. The browser dispatch hits the same Baxia page, the branch
  re-fires, `browser_dispatches < 1` stops further escalation, and the fetch
  fails with the `alibaba_punish` fingerprint. This is the honest best-effort
  outcome, not a bug. Documented as such; real reliability is the deferred
  proxy keystone.
- **[False positive on a benign page mentioning "captcha"/"slide"]** →
  Mitigated by requiring distinctive markers (`_____tmd_____` / `x5secdata` /
  the exact punish phrases), not generic words. A dedicated test asserts a thin
  page with the word "captcha" but no Baxia fingerprint stays bare
  `length_floor`.
- **[Marker drift if Alibaba renames the punish path]** → Low/slow risk; the
  text phrases (incl. the Russian variant) provide redundancy beyond the URL
  token. New variants are a one-line marker addition.

## Migration Plan

Pure additive detector branch — no data, wire, or signature change. Ship behind
no flag (it only activates on the Baxia fingerprint). Rollback = revert the
branch; behavior returns to bare `length_floor`. No deploy coordination needed.
