## Why

The `browser-backend-interface` keystone shipped: the tier now delegates to a swappable `BrowserBackend`, but Camoufox is still the only engine and the default. Camoufox is a dead end *right now* — its pip build pins a stale Firefox, the Playwright-1.60 crash means we're frozen below `<1.60`, and the durable fix (juggler PR #625, `b05563291d`) is merged-but-unreleased with no shipping build. Meanwhile the incident that started all this was a Chromium-class SPA (Trendyol) that a Chromium engine reads trivially. We need to move off Camoufox onto a modern, maintained engine — and rather than guess which one, we measure.

This change runs a **live bake-off** of three candidates behind the existing interface, then commits based on what the numbers show. The keystone makes the two Chromium drop-ins nearly free to wire (each is just a `launch_fn`); the CDP adapter is built once, speculatively, so all three compete on real numbers instead of vibes.

**Bake-off result (2026-06-27, `eval/findings_2026-06-27.md`):** the engines are *complementary, not strictly ranked.* The Chromium drop-ins are fast (~1.4s) but **fail the exact Trendyol/Hepsiburada SPAs that motivated this change** (blocked / empty extraction); `zendriver` (CDP) reads them (md 3.4k / 7k) but is ~4-5x slower (~6.7s, the v1 per-render-launch cost). `rebrowser` is a strict loser (ties patchright on reads, worse on robustness — timed out on Cloudflare). So instead of keeping one, we keep **two** and let them escalate: `patchright` as the fast first rung, `zendriver` as the robust second rung — wired as **two browser tiers ("spheres") on the existing gate→escalate loop**, not a new ladder mechanism.

## What Changes

- **Add three candidate backends behind `BrowserBackend`** (done): `patchright` + `rebrowser` (Chromium drop-ins via `PlaywrightBackend(launch_fn)`), `zendriver` (CDP via a `ZendriverBackend` adapter — proof the interface spans engine *families*). Each with a manifest that surfaces `Unavailable` when its extra is absent.
- **Run the render-layer bake-off** on a browser-stress URL set (the corpus barely reaches the browser tier), scoring SPA-read success + robustness + speed at ~0 LLM quota; record `eval/findings_<date>.md`.
- **Keep two winners as a fast→robust two-tier escalation; prune the loser (`rebrowser`).**
  - `browser` tier (existing slug) → **patchright** (fast Chromium JS render).
  - `browser_robust` tier (new slug) → **zendriver** (robust CDP render).
  - The deterministic playbook gets **one new rule**: gate still thin/blocked after `browser` → escalate to `browser_robust`. Same `next_action_after_gate` machinery, one more rung; each rung capped 1/fetch. **No new escalation mechanism, no change to TIER_ORDER's normal path** (both browser rungs stay out-of-band like browser is today).
  - Fix the decision-log's hardcoded `engine="camoufox"` → the real tier/engine name, so `browser` (patchright) vs `browser_robust` (zendriver) is visible in diagnostics.
- **Flip `settings.browser_backend` default** to `"patchright"` (fast rung) + add `settings.browser_backend_robust = "zendriver"` (robust rung).
- **Gate the Camoufox manifest** to `Unavailable` with the #625 note (re-enable when a build ships commit `b05563291d`). Camoufox code retained behind the gate.
- **Modernize deps:** promote `patchright` + `zendriver` from the `bakeoff` extra to baseline deps; drop `rebrowser`; drop `camoufox[geoip]` (which is what pulls `playwright` transitively, retiring the `<1.60` exposure). *(Ask-first: the dep promotion + camoufox drop.)*
- **Non-goals:** no change to the `BrowserBackend` interface or `RenderedPage`, no change to `TierResult` / the response envelope, no new *escalation* mechanism (the second tier reuses the existing gate→escalate loop).

## Capabilities

### New Capabilities
<!-- none — the interface seam exists; this change populates it + adds a tier rung via the existing escalation -->

### Modified Capabilities
- `browser-backend`: the registry retains **two** engines after the bake-off (`patchright` fast + `zendriver` CDP), not one; default flips off Camoufox; Camoufox gated to `Unavailable` behind the #625 note; the interface is proven engine-family-agnostic by a CDP adapter (`ZendriverBackend`). Selection recorded in `eval/findings_2026-06-27.md`.
- `browser-tier`: browser rendering becomes a **two-rung fast→robust escalation** — `browser` (patchright) tried first, `browser_robust` (zendriver) dispatched by the existing deterministic playbook when the gate is still thin/blocked after the fast rung. Each rung out-of-band and capped 1/fetch; the engine name surfaces in the decision log.

## Impact

- `src/a2web/packages/browser_backends/` — `patchright.py` (kept), `rebrowser.py` (**pruned** — loser), `zendriver.py` (kept).
- `src/a2web/_manifests/browser_backends/` — `patchright.py` + `zendriver.py` kept; `rebrowser.py` + `_common.py` (rebrowser's helper) pruned; `camoufox.py` flipped to `Unavailable`-gated.
- `src/a2web/tiers/__init__.py` (REGISTRY) — register `browser_robust` (a `BrowserTier` driven by the robust backend) alongside the existing out-of-band `browser`.
- `src/a2web/actions/playbook.py` — one new rule: gate thin/blocked after `browser` → escalate to `browser_robust` (capped 1/fetch).
- `src/a2web/fetcher.py` — `_escalate_browser` resolves the fast backend; a sibling robust-escalation path resolves the robust backend; fix `engine="camoufox"` → real tier/engine name in events + diagnostics.
- `src/a2web/settings.py` — `browser_backend` default → `"patchright"`; add `browser_backend_robust = "zendriver"`.
- `src/a2web/state.py` / `routers.py` — a second backend seam for the robust rung (lazy-entered only when the robust escalation fires).
- `pyproject.toml` — promote `patchright` + `zendriver` to baseline deps; drop `rebrowser` + `camoufox[geoip]` (retires the transitive `playwright` / the `<1.60` exposure).
- `eval/findings_2026-06-27.md` — the recorded bake-off result (audit trail for "why these engines").
- `tests/` — real-browser smoke for both rungs (behind the `browser` marker); `select_backend` default test → patchright; a test for the new playbook escalation rule (`browser` thin → `browser_robust`); package-independence + boundary-frozen stay green.
- **Ask-first gates (per CLAUDE.md):** promoting the two engine deps to baseline + dropping camoufox — surfaced at the dependency-touching task.
