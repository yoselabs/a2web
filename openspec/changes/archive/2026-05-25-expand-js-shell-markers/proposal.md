## Why

The block-detector's `_JS_SHELL_ROOT_MARKERS` regex catches React/Vue/Next mount points (`id="__next"`, `id="root"`, `id="app"`, `id="react-root"`, `window.__INITIAL_STATE__`, `<noscript>`) but misses two distinct categories of JS-required pages.

The production bench (v0.21) returned `tier=raw verdict=length_floor` on `https://www.reddit.com/r/LocalLLaMA/`. Diagnostic probes (`eval/spikes/reddit_block_probe.py`, `eval/spikes/reddit_with_cookies_probe.py`, `eval/spikes/cloudflare_bypass_probe.py`) plus implementation-time inspection of the captured 8KB body revealed the actual cause is a **JS-challenge anti-bot interstitial**, not a web-component shell:

```html
<form hidden method="GET" action="/r/LocalLLaMA/">
  <input type="hidden" name="solution" />
  <input type="hidden" name="js_challenge" value="1"/>
  <input type="hidden" name="token" value="..."/>
  <input type="hidden" name="jsc_orig_r" value=""/>
</form>
```

The body is a Snoo logo + a hidden JS challenge form. Solving the challenge in a real browser produces the actual SPA. None of the existing markers (React mount points, `<noscript>`, Cloudflare interstitial) match this shape, so the planner gets `suggested_tier=None` and the browser tier never fires.

Confirmed empirically:
- Raw curl_cffi returns 200 OK + 8KB JS-challenge body. No React/Vue/Next markers.
- Camoufox browser tier loads the same URL successfully (1MB DOM, real title, 68 post-link references) — JS execution solves the challenge automatically.
- `old.reddit.com` is also 403'd for unauth curl_cffi (the v0.20-backlog fallback option is dead).
- Cookies / OAuth are not needed — the marker → browser escalation path is the right answer.
- `curl_cffi impersonate=chrome` already bypasses Cloudflare; "403 → browser" routing is unjustified by current evidence.

Separately, web-component SPAs (Lit-based sites, hand-rolled custom elements) are a real second category our markers miss today. We don't have a live failing case for it, but the fix is one regex alternation and pre-covers the next site that ships one.

## What Changes

- **Add Reddit-shaped JS-challenge marker.** Recognize the hidden challenge form pattern: `name="js_challenge"` and/or `name="jsc_orig_r"`. Empirically validated against the captured Reddit fixture; Reddit-specific enough that false-positive risk is essentially zero.
- **Add generic custom-element marker.** Regex `<[a-z][a-z0-9]*-[a-z][a-z0-9-]*` matches any HTML5 custom-element opening tag (per the HTML Living Standard §4.13, custom elements MUST contain a hyphen and start with a lowercase ASCII letter). Pre-covers Lit-based SPAs and any other web-component shell we encounter.
- **No planner change.** The existing `EscalateBrowser` rule already fires when `block_detector` returns `suggested_tier="browser"`; this change just makes more pages reach that signal.
- **No new tiers, no behavior change for sites without markers.** Pages that fail length-floor without any marker continue to return `length_floor` without escalation, as today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `quality-gate`: extends the JS-required heuristic to recognize (a) JS-challenge anti-bot interstitials (Reddit pattern: hidden `name="js_challenge"` / `name="jsc_orig_r"` form fields), and (b) web-component SPAs (custom elements per HTML5 spec). Sites returning a thin body of either shape now correctly route to browser-tier escalation.

## Impact

- **Code**: ~5 lines in `src/a2web/packages/block_detector.py` (regex expansion). 2-3 new tests in `tests/packages/block_detector/` covering the Reddit fixture + a synthetic custom-element fixture + a negative case (static HTML with hyphenated attribute values, not tag names).
- **Behavior**: Reddit listings + threads (which serve a JS-challenge interstitial to raw) now reach the browser tier instead of failing with `length_floor`. The custom-element regex additionally pre-covers any future web-component SPA we encounter.
- **Cost**: Adds one browser dispatch per affected fetch (~$0/call but ~30s + memory). Already capped at 1 dispatch per fetch by the planner.
- **No dependencies, no API surface changes, no envelope changes.**
- **Backlog cleanup**: closes the `Reddit old.reddit raw-tier fetch failure` item (root cause was upstream of the handler).
