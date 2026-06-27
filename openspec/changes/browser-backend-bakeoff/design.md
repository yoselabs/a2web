## Context

`browser-backend-interface` extracted a domain-free `BrowserBackend` Protocol (`render(url, *, cookies, budget_s, js_heavy) -> RenderedPage`) and moved Camoufox behind it as `PlaywrightBackend(camoufox_launcher)`. The seam is proven but unpopulated: Camoufox is the only backend and the default, and it's a dead end today (stale FF pin, frozen below Playwright 1.60, #625 merged-but-unreleased). The keystone makes Chromium drop-ins (`patchright`, `rebrowser-playwright`) nearly free — each is a new `launch_fn` for the existing `PlaywrightBackend`. The one engine that costs real work is `zendriver`: it speaks CDP, not the Playwright API, so it needs a bespoke adapter. The user chose to build all three and let corpus numbers decide, rather than trust the desk research (which favored patchright on maintenance and zendriver on raw stealth).

Constraints: the `BrowserBackend` interface and `RenderedPage` are frozen (this change satisfies the contract, it doesn't touch it). `TierResult` / response envelope unchanged. The tier must never be engine-less — Camoufox stays selectable until the winner is green. New top-level deps and the dep bump/drop are ask-first gates.

## Goals / Non-Goals

**Goals:**
- Stand up three candidate backends behind the interface: two Chromium drop-ins + one CDP adapter.
- Score them on the live corpus (SPA-read + robustness + speed) and record the result.
- Commit to exactly one winner; prune the losers to zero residue.
- Flip the default to the winner; gate Camoufox to `Unavailable` (reversible when #625 ships).
- Modernize deps: drop direct `playwright` + `camoufox`, retire the `<1.60` pin, bump the rest.

**Non-Goals:**
- Changing the `BrowserBackend` interface or `RenderedPage` (frozen).
- Changing `TierResult` or the response envelope.
- Deleting Camoufox (gated, not removed — it's the known fingerprint-strong fallback).
- A *new escalation mechanism* (the second engine reuses the existing gate→escalate loop), or wiring stealth as the primary selection axis.

## Decisions

**D0 — Bake-off outcome: keep two as a fast→robust ladder, not one (supersedes the "keep one" framing).** The render-layer bake-off (`eval/findings_2026-06-27.md`) showed the engines are *complementary, not strictly ranked*: the Chromium drop-ins are fast (~1.4s) but fail the Trendyol/Hepsiburada SPAs that motivated the change; zendriver (CDP) reads them but is ~4-5x slower (per-render-launch cost). Forcing one would either lose the incident-class reads (patchright-only) or tax every browser escalation 4-5x (zendriver-only). So we keep **patchright (fast)** + **zendriver (robust)** and escalate between them; **rebrowser** is the sole prune (ties patchright on reads, worse on robustness — Cloudflare timeout).

**D0a — Two engines = two tiers ("spheres") on the EXISTING escalation; reuse the laddering, don't reinvent it.** Rather than a bespoke backend-ladder inside the browser tier, model fast/robust as two out-of-band browser tiers walked by the deterministic playbook — the same `decide_next` / `_RULES` mechanism that already escalates `raw→jina` and dispatches `browser`. Maximal reuse — the only changes to the escalation machinery:

- **Reuse the existing `EscalateBrowser` action and the existing `gate_browser_signal` rule** — *widen its cap* from `browser_dispatches < 1` to `< 2`. A successful fast render makes the gate verdict `ok`, so the rule (which requires `verdict is not ok`) won't fire again; a thin/blocked fast render leaves the gate still wanting browser, so the *same rule* fires a second time. **No new action, no new rule, no new cap field.**
- **Reuse the single `_escalate_browser` handler** — parameterize it by rung from `fc.browser_dispatches` (0 → fast: tier `browser`, `fc.browser_backend`; 1 → robust: tier `browser_robust`, `fc.browser_robust_backend`). Not copied into a `_escalate_browser_robust` twin.
- **New, but irreducible:** a `browser_robust` tier instance (a second `BrowserTier`, priority=-1) in `REGISTRY`, and a second engine *resource* (D0b). These are "a second tier + a second engine available," not escalation infrastructure.

*Why not a backend-ladder inside one tier:* that invents a second escalation path parallel to the playbook; the user's constraint was "use the same architecture, don't build separate mechanisms for separate ladders." *Why not a new action/rule:* the existing browser rule already encodes "gate still wants browser, under cap" — widening the cap is strictly less new vocabulary than a parallel rule.

**D0b — Second backend seam mirrors the first.** The robust rung needs zendriver only when it fires, so it gets its own `Lazy[BrowserBackend]` tool-seam kwarg (`browser_robust_backend`) + `build_browser_robust_backend` provider — the exact lazy-first-use pattern the fast `browser_backend` already uses. `settings.browser_backend="patchright"` (fast) + `settings.browser_backend_robust="zendriver"` (robust); `select_backend_named(settings, name)` resolves either from the manifest registry. The decision-log's hardcoded `engine="camoufox"` becomes the real tier/engine name so operators see which rung ran.

**D1 — Build all three, then prune (vs. ship patchright on research).** The user opted for empirical confidence over speed. The marginal cost is asymmetric: the two drop-ins are ~free (launch_fn swaps), so the only real spend is the zendriver adapter + the live-quota corpus run. Building all three buys a recorded, defensible engine choice and a one-time proof that the interface spans engine families. The losers are deleted, so the end-state cost is identical to shipping one — we just pay a transient bake-off cost.

**D2 — Chromium drop-ins are `launch_fn`s, not new classes.** `patchright` and `rebrowser-playwright` are API-compatible with Playwright; `PlaywrightBackend` already takes a `launch_fn`. So `patchright.py` / `rebrowser.py` in `packages/browser_backends/` are thin: a `*_launcher()` returning the engine's `async_playwright`-shaped CM, plus a manifest. No new pooling/stderr/scroll logic — they inherit all of it. This is the payoff of the keystone.

**D3 — `ZendriverBackend` is a fresh adapter, not a `PlaywrightBackend` variant.** zendriver drives a browser over CDP with its own `Tab`/`Browser` objects — no `launch_fn` that yields a Playwright `Browser`. So it implements `BrowserBackend` directly: `render()` opens a tab, navigates with the `budget_s` cap, seeds `BackendCookie`s via CDP `Network.setCookie`, captures outer HTML, and maps failures to `RenderOutcome.{timeout,error,unavailable}`. It owns its own lifecycle (`__aenter__`/`__aexit__`) and reuses the package-side helpers where they're engine-neutral (`_summarize_exc`, the markdown-floor scroll heuristic conceptually, the `RenderedPage` assembly). It must NOT leak a CDP session/`Tab` — only `RenderedPage` crosses the boundary (the interface's whole point). Pooling: zendriver's per-host reuse is simpler than Playwright contexts; v1 may launch per-render and optimize later if it wins.

**D4 — Bake-off harness reuses the eval corpus, not a new framework.** The corpus + `make bench` already score systems on quality/cost/clarity/conformance over live network. The bake-off is "run the browser-escalation cases through each candidate as the active backend." Mechanism: a small CLI/script that sweeps `settings.browser_backend` over `{patchright, rebrowser, zendriver}` and replays the SPA/robustness cases, capturing SPA-read success (did we get usable markdown?), robustness (block/challenge survival), and speed (`wall_ms`). Output → `eval/findings_<date>.md`. This is live-network + spends quota, so it's manual, never in `make check`.

**D5 — Camoufox gated, not deleted; gate is reversible.** Flip `_manifests/browser_backends/camoufox.py` to return `Unavailable("camoufox: FF build lacks juggler #625 / b05563291d; re-enable when shipped")`. The `PlaywrightBackend` + `camoufox_launcher` code stays. Lifting the gate later is a one-line manifest edit once a Camoufox build ships the commit — cheap to re-enable, which is why we keep the code.

**D6 — Dep surgery happens last, after both kept engines are green.** Order: add candidate extras → bake-off → keep patchright+zendriver, prune rebrowser → THEN promote `patchright`+`zendriver` from the `bakeoff` extra to baseline deps, drop `rebrowser` + `camoufox[geoip]`. patchright self-vendors playwright-core and zendriver is CDP-native, so dropping `camoufox[geoip]` removes the only thing pulling `playwright` transitively — the `<1.60` exposure retires with it. The gated Camoufox code stays but its dep leaves; re-enabling #625 later means re-adding `camoufox` + flipping the manifest. Each dep edit is an ask-first checkpoint.

## Risks / Trade-offs

- **[zendriver adapter is real work that may be thrown away]** → It's the price of D1's empirical confidence, and the user chose it knowingly. Mitigation: keep the v1 adapter minimal (per-render launch, no pool) so the sunk cost is bounded if it loses; the cross-family proof has standalone value (it hardens the interface) even if the code is removed.
- **[Live-quota bake-off cost]** → Scope the bake-off to the browser-escalation subset of the corpus (the cases that actually reach the browser tier), not the full suite. Record the exact case set in findings.
- **[A drop-in's stealth patches drift / break on a Playwright bump]** → This is the Camoufox failure mode repeating. Mitigation: the winner's smoke test runs under the `browser` marker; the robustness axis is scored at selection time, and the gated-Camoufox fallback remains one manifest edit away.
- **[New boundary types from the CDP adapter break the package-independence invariant]** → If `ZendriverBackend` needs any new value object, it must be package-owned + domain-free + added to `_FROZEN_BOUNDARY_TYPES`; the existing `test_packages_independence` / `test_packages_boundary_frozen` tests are the guard.
- **[Default flip changes fresh-install rendering behavior]** → Intended. Mitigation: the winner's dep is non-optional (installed by default), and the real-browser smoke check covers the new default before merge.

## Migration Plan

1. Add the three candidate backends + manifests + extras (ask-first on the deps).
2. Run the bake-off; record `eval/findings_<date>.md`.
3. Pick the winner; delete loser code/manifests/extras.
4. Flip `settings.browser_backend` default; gate Camoufox.
5. Drop `playwright`+`camoufox`, retire `<1.60`, bump engine deps (ask-first).
6. Re-bless the winner's smoke + `select_backend` default test; full `make check`.

Rollback: revert the default flip (back to `"camoufox"`) and lift the Camoufox gate — Camoufox code never left the tree, so rollback is a settings + manifest revert, not a re-implementation.

## Open Questions

- Final winner — resolved by the bake-off, recorded in findings (not pre-decided here).
- Whether `zendriver` v1 needs per-host pooling or per-render launch suffices — decide from the speed axis numbers; default to per-render unless it loses on speed alone.
