## 1. Detector branch

- [x] 1.1 Add Baxia marker constants to `src/a2web/packages/block_detector.py`: a URL/path matcher (`/_____tmd_____/punish`, `x5secdata`, `x5step`), a body-phrase matcher (`unusual traffic from your network`, `Please slide to verify`, `Captcha Interception`, `Пройдите проверку`), and an HTML-token matcher (`_____tmd_____`, `baxia`, `nocaptcha`, `slidecaptcha`).
- [x] 1.2 Add the `alibaba_punish` detector branch in `evaluate(...)` alongside the `turnstile`/`akamai_bmp`/`anubis` branches (before the generic JS-shell and bare-`length_floor` fallthroughs). Fire on the marker alone, independent of `content_md` length; check the final URL and the raw HTML/body.
- [x] 1.3 Return `BlockResult(verdict=BlockVerdict.anti_bot, subsystem="alibaba_punish", escalation=EscalationSignal(next_tier="browser", reason="alibaba_punish"))` from the branch (`anti_bot` mirrors the sibling anti-bot branches; honest verdict when escalation is capped). Confirm no change needed to `EscalationSignal`, the planner (`_decide_gate_browser_signal`), or the browser tier.

## 2. Tests

- [x] 2.1 Test: AliExpress punish URL (`/_____tmd_____/punish?x5secdata=...&x5step=1`) with 0 extracted chars yields `subsystem="alibaba_punish"` and `escalation.next_tier="browser"`.
- [x] 2.2 Test: a short body containing `unusual traffic from your network … Please slide to verify` (no URL token) is recognized regardless of length.
- [x] 2.3 Test: the `aliexpress.ru` Russian variant (`Пройдите проверку` + `_____tmd_____` token) is recognized.
- [x] 2.4 Test (no false positive): a 300-char page mentioning `captcha` in prose but with none of the Baxia markers returns plain `length_floor` with `subsystem is None` and `escalation is None`.
- [x] 2.5 Test (regression): an existing JS-shell / turnstile / bare-length_floor case is unchanged by the new branch ordering.

## 3. Gate verification

- [x] 3.1 Run `make check` (lint + ty + test, coverage ≥85%) and confirm green.
- [x] 3.2 Manual sanity: `uv run a2web web fetch_raw --url="https://www.aliexpress.com/wholesale?SearchText=headphones" --debug` shows the gate emitting `subsystem=alibaba_punish` and a browser dispatch attempt in diagnostics (instead of the prior bare `length_floor` stop). Note: success depends on the egress IP not being Baxia-flagged — a flagged IP correctly fails with the `alibaba_punish` fingerprint.

## 4. Backlog capture (deferred scope)

- [x] 4.1 Add a `BACKLOG.md` entry "Reliable AliExpress / Alibaba access" recording the deferred gaps from this session's PoCs: browser tier ignoring `proxy_url` (`browser.py:135`, the keystone), KZ residential proxy provisioning, per-IP pacing/rotation, an AliExpress SSR/XHR product-JSON handler, and the probabilistic-ceiling reality (Baxia is IP-reputation-driven; CAPTCHA-solving is out of scope). Note that the user has non-KZ residential proxies that unlock once the browser-through-proxy keystone lands.
