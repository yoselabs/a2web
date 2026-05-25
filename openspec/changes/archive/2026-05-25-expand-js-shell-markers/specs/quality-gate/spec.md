## ADDED Requirements

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
