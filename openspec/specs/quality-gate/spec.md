# quality-gate Specification

## Purpose
TBD - created by archiving change pr7c-browser-tier. Update Purpose after archive.
## Requirements
### Requirement: Jina stub recognized as paywall

The quality gate SHALL recognize jina-tier responses carrying upstream-error stubs as `Verdict.paywall` (not `Verdict.length_floor`), so the existing archive escalator can fire. The rule SHALL match responses where ALL of the following hold:

1. The fetch tier is `jina` (recorded on the gate input, not inferred from the body).
2. The body length is below 2,048 characters.
3. The body matches the regex `Target URL returned error 40[13]` (covers both `401 Unauthorized` and `403 Forbidden` — the two jina-stub status codes that indicate paywall / auth).

When the rule matches, the gate SHALL set `verdict = Verdict.paywall` and `subsystem = "jina_stub"`. `suggested_tier` SHALL be left `None` — the orchestrator's existing archive-on-paywall playbook handles the next step.

#### Scenario: NYT-shape jina stub triggers paywall verdict

- **WHEN** the gate evaluates a jina-tier response whose body is `Warning: Target URL returned error 403: Forbidden\n...` and total length is ~500 chars
- **THEN** `verdict == Verdict.paywall`, `subsystem == "jina_stub"`

#### Scenario: 401 Unauthorized stub also triggers paywall

- **WHEN** the gate sees a jina response with `Target URL returned error 401: Unauthorized`
- **THEN** the same paywall verdict fires

#### Scenario: Long jina response is not misclassified

- **WHEN** a jina response succeeds normally (10KB+ markdown body that happens to contain the substring `error 403` in quoted text)
- **THEN** the rule does not fire (body length floor enforces this); verdict follows the normal classifier path

### Requirement: Thin browser response on JS-heavy host downgrades to length_floor

When the fetch tier is `browser` AND the response is HTTP 200 AND the rendered body is <1,024 chars AND the host matches the `JS_HEAVY_HOSTS` set, the gate SHALL emit `verdict = Verdict.length_floor` so the orchestrator continues escalation (typically to archive). The `JS_HEAVY_HOSTS` seed set lives in `src/a2web/packages/quality_gate/` (or wherever the gate lives) and initially contains: `x.com`, `twitter.com`, `instagram.com`, `tiktok.com`, `trendyol.com`, `aliexpress.com`. The set SHALL be exposed for extension via a settings-backed override (`A2WEB_JS_HEAVY_HOSTS` env, comma-separated).

#### Scenario: X.com thin browser response is failed

- **WHEN** the browser tier returns 200 OK with a body of ~480 chars (the X "JavaScript is disabled" stub) for host `x.com`
- **THEN** `verdict == Verdict.length_floor` (escalation continues; orchestrator does not return this as a successful fetch)

#### Scenario: Thin browser response from non-listed host is not downgraded

- **WHEN** the browser tier returns 200 OK with a 500-char body from `someblog.example.com` (not in JS_HEAVY_HOSTS)
- **THEN** the gate uses the normal classifier path; the rule does not fire

#### Scenario: Custom host added via settings override is matched

- **WHEN** `A2WEB_JS_HEAVY_HOSTS="custom.example.com"` is set and the browser tier returns a thin response for that host
- **THEN** the rule fires for `custom.example.com`

### Requirement: JS-shell marker detection recognizes JS-challenge interstitials and web-component SPAs

The `_JS_SHELL_ROOT_MARKERS` regex used by `block_detector.evaluate(...)` SHALL recognize JS-challenge anti-bot interstitials and web-component SPA shells in addition to React/Vue/Next-style mount-point markers. When `len(content_md) < LENGTH_FLOOR` AND the response body contains a `<script>` tag AND ANY of the following marker patterns match, the gate SHALL return `BlockResult(verdict=BlockVerdict.length_floor, subsystem="js_required", suggested_tier="browser")`:

Existing markers (unchanged):
- `id="__next"` (Next.js)
- `id="root"` (Create React App / generic React)
- `id="app"` (Vue / generic)
- `id="react-root"` (legacy React)
- `window.__data__` (Nuxt / SSR data)
- `window.__INITIAL_STATE__` (generic SSR)
- `<noscript` (SPA fallback element)

New markers:
- `name="js_challenge"` (Reddit JS-challenge hidden form field — empirically validated against the captured Reddit shell fixture)
- `name="jsc_orig_r"` (Reddit JS-challenge "original request" field — Reddit-specific enough to have near-zero false-positive surface)
- A generic custom-element pattern: any opening tag of the form `<[a-z][a-z0-9]*-[a-z][a-z0-9-]*` (per HTML5 §4.13, custom-element tag names MUST contain a hyphen and start with a lowercase ASCII letter)

The existing three-condition gate (length floor AND `<script>` present AND marker present) SHALL remain unchanged; only the marker set expands. Sites without ANY marker SHALL continue to return `BlockResult(verdict=BlockVerdict.length_floor)` with `suggested_tier=None`, preserving today's behavior.

#### Scenario: Reddit JS-challenge interstitial is recognized as JS-required

- **WHEN** the gate evaluates a response with `content_md` below the length floor, body containing `<script>`, and body containing a hidden form with `<input ... name="js_challenge" ...>` (the Reddit anti-bot challenge shape)
- **THEN** `GateResult.verdict == Verdict.length_floor`, `subsystem == "js_required"`, `suggested_tier == "browser"`

#### Scenario: Generic custom-element shell is recognized as JS-required

- **WHEN** the gate evaluates a response with `content_md` below the length floor, body containing `<script>`, and body containing a hyphenated custom element opening tag (e.g., `<my-widget>`, `<lit-element>`, `<faceplate-tracker>`)
- **THEN** `GateResult.verdict == Verdict.length_floor`, `subsystem == "js_required"`, `suggested_tier == "browser"`

#### Scenario: Static HTML with no markers preserves existing behavior

- **WHEN** the gate evaluates a response with `content_md` below the length floor and a `<script>` tag but NO matching marker (e.g., a plain HTML stub with no SPA roots, no custom elements, no challenge form, no window-state dumps)
- **THEN** `GateResult.verdict == Verdict.length_floor`, `subsystem is None`, `suggested_tier is None`

#### Scenario: Hyphenated attribute values do not trigger false positives

- **WHEN** the gate evaluates a static HTML page containing hyphenated attribute values (e.g., `data-id="x-y-z"`, `class="my-component"`) but no hyphenated tag names and no challenge form
- **THEN** the generic custom-element regex SHALL NOT match (the regex requires `<` immediately before the hyphenated lowercase token), and the gate SHALL NOT set `suggested_tier="browser"`

#### Scenario: Content above length floor is not classified as JS-required regardless of markers

- **WHEN** the gate evaluates a response with `content_md` above `LENGTH_FLOOR` that ALSO contains custom elements or a challenge-shaped form (e.g., a server-rendered page with progressive enhancement)
- **THEN** the marker logic SHALL NOT fire and the verdict SHALL be `Verdict.ok`

#### Scenario: Generic `name="solution"` alone does NOT trigger

- **WHEN** the gate evaluates a thin response containing `<input name="solution">` (e.g., a math quiz or exam site) but no `js_challenge` / `jsc_orig_r` / custom-element / React markers
- **THEN** the gate SHALL NOT set `suggested_tier="browser"` (we deliberately excluded the generic `solution` field name to avoid false positives on legitimate sites)

### Requirement: BlockResult carries a typed EscalationSignal instead of a string suggested_tier

`BlockResult` in `src/a2web/packages/block_detector.py` SHALL replace its `suggested_tier: str | None = None` field with `escalation: EscalationSignal | None = None`. `EscalationSignal` lives in `src/a2web/packages/escalation.py` — package-owned so block_detector can import it without crossing the packages-independence boundary.

Detector branches that previously set `suggested_tier="browser"` SHALL set `escalation=EscalationSignal(next_tier="browser", reason="<subsystem>")` where `<subsystem>` is the matching marker family name (`js_required`, `anubis`, `turnstile`, `akamai_bmp`, etc.).

Detector branches that previously set `suggested_tier="tls_impersonate"` SHALL set `escalation=EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam")`.

The block detector remains policy-free — it emits typed evidence; the planner decides whether to act. Behavior visible to callers is unchanged; only the field type changes.

#### Scenario: JS-required marker yields typed escalation

- **WHEN** the gate evaluates a thin response containing web-component or React markers + `<script>`
- **THEN** `BlockResult.escalation == EscalationSignal(next_tier="browser", reason="js_required")` and downstream the planner reads the typed signal

#### Scenario: Cloudflare interstitial yields typed escalation

- **WHEN** the gate sees a "Just a moment..." interstitial with `cf-chl-bypass` markers
- **THEN** `BlockResult.escalation == EscalationSignal(next_tier="tls_impersonate", reason="cf_iuam")`

#### Scenario: Healthy page emits no escalation

- **WHEN** the gate evaluates a normal article that passes all checks
- **THEN** `BlockResult.escalation is None` (semantically identical to the previous `suggested_tier is None`)

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
failure verdict when escalation is capped on an already-flagged IP. `curl_cffi`
follows the redirect onto the punish page, whose `raw_html` carries the markers,
so no final-URL parameter is threaded into the detector.

The Baxia fingerprint matches when `raw_html` contains ANY of the following:

- the punish path token `_____tmd_____` (e.g. from `/_____tmd_____/punish`), or
  the `x5secdata` / `x5step` punish-flow query tokens;
- the AWSC slider widget ids/classes `slidecaptcha`, `nocaptcha`, or
  `nc_iconfont`, or the anti-bot system name `baxia`;
- the localized interstitial text `slide to verify` (aliexpress.com),
  `Captcha Interception` (aliexpress.com punish title), or `Пройдите проверку`
  (aliexpress.ru).

Unlike the JS-shell rule, this branch SHALL fire on the marker alone,
independent of extracted content length, so a punish page surfaced by the
browser tier (when the egress IP is already flagged) is detected as well. The
branch SHALL be evaluated alongside the existing anti-bot branches
(`turnstile` / `akamai_bmp` / `anubis`), before the generic JS-shell and the
bare-`length_floor` fallthrough. Escalation remains bounded by the
orchestrator's existing `browser_dispatches < 1` cap; no new escalation type or
planner rule is introduced.

This requirement SHALL NOT change behavior for responses that do not match the
Baxia fingerprint: a thin page without the fingerprint SHALL continue to return
`BlockResult(verdict = BlockVerdict.length_floor)` with `subsystem` and
`escalation` unset, exactly as today (in particular, prose merely mentioning the
word `captcha` SHALL NOT match).

#### Scenario: AliExpress Baxia punish escalates to browser

- **WHEN** the raw tier returns HTTP 200 whose `raw_html` references the punish
  path (`_____tmd_____` + `x5secdata`/`x5step`) and trafilatura extracts 0 chars
- **THEN** `BlockResult.verdict == BlockVerdict.anti_bot`,
  `subsystem == "alibaba_punish"`, and
  `escalation == EscalationSignal(next_tier="browser", reason="alibaba_punish")`

#### Scenario: Baxia body phrase is recognized regardless of length

- **WHEN** any tier returns a body containing `Sorry, we have detected unusual
  traffic from your network. Please slide to verify` (a short interstitial well
  under the length floor) with no `_____tmd_____` token
- **THEN** `subsystem == "alibaba_punish"` and `escalation.next_tier == "browser"`

#### Scenario: Russian-locale punish interstitial is recognized

- **WHEN** the browser tier returns the `aliexpress.ru` punish page whose body
  contains `Пройдите проверку` and HTML references the `_____tmd_____` token
- **THEN** `subsystem == "alibaba_punish"` and `escalation.next_tier == "browser"`
  (the `browser_dispatches` cap then prevents further escalation, and the fetch
  fails with the `alibaba_punish` fingerprint visible in the decision log)

#### Scenario: Thin non-Baxia page preserves existing behavior

- **WHEN** a tier returns a 300-char body that mentions the word `captcha` in
  prose but carries none of the Baxia tokens, phrases, or markers
- **THEN** `BlockResult.verdict == BlockVerdict.length_floor`, `subsystem is
  None`, and `escalation is None` (no false-positive escalation)

