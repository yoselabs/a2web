## Context

`block_detector.evaluate(...)` decides whether a fetched body is real content, a block page, or a JS-required SPA shell. When `len(content_md) < LENGTH_FLOOR`, it checks `raw_html` against three escalation paths:

1. Cloudflare interstitial markers → `suggested_tier="tls_impersonate"`
2. Generic block-page regex → `block_page_detected`
3. `<script>` present AND `_JS_SHELL_ROOT_MARKERS` present → `length_floor + suggested_tier="browser"`
4. Otherwise → plain `length_floor` with no suggestion

The planner only escalates to browser when `suggested_tier == "browser"`. Branch 3 is the only path that gets there from the raw tier.

Today's `_JS_SHELL_ROOT_MARKERS` regex:

```python
re.compile(
    r'id="__next"'              # Next.js
    r'|id="root"'               # CRA / generic React
    r'|id="app"'                # Vue / generic
    r'|id="react-root"'         # legacy React
    r'|window\.__data__'        # Nuxt / SSR data dump
    r'|window\.__INITIAL_STATE__'
    r'|<noscript',              # SPA usually has a no-js fallback
    re.IGNORECASE,
)
```

This is React/Vue/Next-centric and misses two categories.

**Category 1 — JS-challenge anti-bot interstitial (Reddit today).** Inspecting the captured 8KB body from `https://www.reddit.com/r/LocalLLaMA/` revealed it is NOT a web-component SPA shell. It is an anti-bot challenge page:

```html
<main><div class='logo'><svg>Snoo logo</svg></div></main>
<form hidden method="GET" action="/r/LocalLLaMA/">
  <input type="hidden" name="solution" />
  <input type="hidden" name="js_challenge" value="1"/>
  <input type="hidden" name="token" value="..."/>
  <input type="hidden" name="jsc_orig_r" value=""/>
</form>
```

JavaScript on the page computes `solution` and resubmits, redirecting to the real SPA. Without JS execution, raw tier sees only the challenge body — thin enough to fall below `LENGTH_FLOOR` but with no React/Vue/Next markers. The fix is recognizing the hidden challenge form by its field names (`name="js_challenge"`, `name="jsc_orig_r"`) — these are Reddit-specific enough that false positives are unlikely.

**Category 2 — Web-component SPAs.** Sites that ship a shell of `<custom-element>` tags (Lit-based apps, hand-rolled web components) currently fall through markers. We don't have a live failing case in the corpus, but the fix costs one regex alternation and pre-covers the category proactively.

The current marker list grew reactively per site (Trendyol, AliExpress…). This change adds **two categorical patterns** — one for JS-challenge interstitials, one for web-component SPAs — that each cover a wider class than per-site markers.

## Goals / Non-Goals

**Goals:**
- Recognize Reddit's JS-challenge interstitial (via `js_challenge` / `jsc_orig_r` form-field markers).
- Recognize any web-component SPA shell (via generic custom-element regex).
- Zero behavior change for sites without either marker (no new false positives).
- Single small, contained change to one regex; no planner / tier / handler edits.
- Reproducible probes in `eval/spikes/` documenting the evidence.

**Non-Goals:**
- Adding a "403 → browser" planner rule. Probe evidence shows curl_cffi+impersonate already bypasses Cloudflare, and no case has yet been found where `raw=403 ∧ browser=200`. Deferred to backlog pending evidence.
- Adding a content-density heuristic (text-to-script ratio). Marker-based detection is sufficient; density would earn its complexity only if marker drift keeps happening.
- Auto-rewriting Reddit URLs to `old.reddit.com` (probe confirmed it's also 403'd; not a viable path).
- Reading Chrome cookies for Reddit (the user's logged-in session). Cookie-based unblock is a wider design topic; out of scope here.
- Restructuring the Reddit handler. The handler is innocent in this failure; the bug is upstream in marker detection.

## Decisions

### D1 — Add Reddit JS-challenge markers: `name="js_challenge"` and `name="jsc_orig_r"`

These are field names in the hidden challenge form that Reddit serves to unauth raw clients. Both are present in the captured Reddit fixture. `jsc_orig_r` is the most distinctive — `jsc` stands for "JavaScript challenge" — making it Reddit-specific enough that the false-positive surface is essentially zero. We include both as an OR (defense in depth: if Reddit drops one field name in a future version, the other likely survives).

Why these markers and not the more generic `name="solution"`? Because "solution" is a common form-field name across the web (math quizzes, exam sites, captchas-in-general). `js_challenge` and `jsc_orig_r` together don't appear in any legitimate non-Reddit context I can think of.

### D2 — Add a generic custom-element regex: `<[a-z][a-z0-9]*-[a-z][a-z0-9-]*`

HTML5 custom-element naming rules (W3C HTML Living Standard, §4.13) require:
- A hyphen in the tag name (this is what distinguishes them from built-in HTML tags)
- Tag name starts with a lowercase ASCII letter
- Contains only lowercase letters, digits, and hyphens

The regex `<[a-z][a-z0-9]*-[a-z][a-z0-9-]*` matches the *opening* of any custom element: `<my-widget`, `<shreddit-app`, `<faceplate-tracker`, `<lit-element`, etc. It does not match attributes that contain hyphens (`data-foo="x"`) because those don't have `<` immediately before the lowercase letter.

This catches the whole category in one shot: Reddit's web-component shell, Lit-based SPAs, any future custom-elements framework, and even hand-rolled `<x-foo>` patterns.

### D3 — Composition: regex is OR'd with existing markers

```python
_JS_SHELL_ROOT_MARKERS = re.compile(
    r'id="__next"'
    r'|id="root"'
    r'|id="app"'
    r'|id="react-root"'
    r'|window\.__data__'
    r'|window\.__INITIAL_STATE__'
    r'|<noscript'
    r'|name="js_challenge"'                          # NEW — Reddit JS challenge
    r'|name="jsc_orig_r"'                            # NEW — Reddit JS challenge
    r'|<[a-z][a-z0-9]*-[a-z][a-z0-9-]*',             # NEW — generic custom element
    re.IGNORECASE,
)
```

The existing rule context still applies: marker match alone does not trigger escalation — the body must also be under `LENGTH_FLOOR` AND contain a `<script>` tag. Three conditions in series remain the gate. (Reddit's challenge body has a `<script>` tag for solving the challenge, so this condition is satisfied.)

### D4 — No planner or browser-tier change

The whole point of the existing `_JS_SHELL_ROOT_MARKERS → suggested_tier="browser"` design is that **marker detection feeds the planner without code changes downstream**. We honor that pattern.

### D5 — Keep markers list, not move to density heuristic

A density heuristic ("text-to-script ratio < threshold → browser") was considered. Decision: defer.

| Approach | Pro | Con |
|---|---|---|
| Markers (current path) | Robust, explicit, low FP rate, no thresholds to tune | Reactive — site changes break detection until regex updated |
| Density heuristic | Proactive — catches all JS-shell variants | Threshold-dependent (FP/FN tradeoff), needs tuning, opaque to maintainers |

The custom-element regex adds enough proactive coverage that we don't need the density approach yet. If marker drift keeps happening (3+ more cases in 6 months), revisit.

## Risks / Trade-offs

### False positive: hand-coded hyphenated tags

A static HTML page that happens to contain a hyphenated tag name (e.g., a tutorial showing `<my-element>` as a code example, escaped in `<pre>` blocks) could match the custom-element regex. Mitigation: the rule requires ALL THREE of `(content_md < LENGTH_FLOOR) AND (<script> present) AND (marker present)`. A static tutorial page big enough to discuss custom elements would have content_md well above the length floor and would not be misclassified.

If a future site fits all three conditions but is genuinely static (no JS needed), the cost is one wasted browser dispatch (~30s + memory) and a fallback to whatever raw produced. Not a regression — just slow on that specific case.

### False positive: legitimate form with `name="solution"`

We deliberately did NOT include `name="solution"` as a marker because it appears in legitimate non-Reddit contexts (math quizzes, exam sites, generic captchas). `name="js_challenge"` and `name="jsc_orig_r"` are Reddit-specific enough that the false-positive surface is essentially zero. If a different site adopts the same pattern, we'd want to recognize it the same way — that's a feature, not a bug.

### Coverage gap: SSR sites with custom elements

A site that server-side-renders content but ALSO uses custom elements (progressive enhancement) would have content_md above the length floor → not flagged → handled normally. This is correct behavior. The marker only matters when raw extraction got nothing.

### Probe evidence is point-in-time

Reddit could change its challenge form field names tomorrow. The Reddit-specific markers would go stale. Mitigation: the generic custom-element regex would still hold for the post-challenge SPA shell IF Reddit ever serves it raw (uncertain), and we can always add new markers reactively. The structural lesson is that the marker list will keep growing — that's the cost of marker-based detection vs. a density heuristic, and we've accepted that trade-off (see D5).

### Backlog cleanup

This change closes one backlog item (Reddit old.reddit raw-tier fetch failure, 2026-05-24) and reframes a second (the v0.20 affordances production-readiness "Reddit anti-bot" line item). Open a new backlog item: "Investigate 403 → browser escalation when a probe finds a site with `raw=403 ∧ browser=200`."

## Probes referenced

- `eval/spikes/reddit_block_probe.py` — initial 3-URL probe showing raw=200 thin body, old.reddit=403, json-api=403.
- `eval/spikes/reddit_with_cookies_probe.py` — proves Camoufox loads Reddit successfully (1MB DOM, 68 post links). Cookie path was inconclusive (Chrome was running, Keychain locked) but not load-bearing for the fix.
- `eval/spikes/cloudflare_bypass_probe.py` — proves curl_cffi+impersonate already bypasses Cloudflare; no "403 → browser" case found yet.
