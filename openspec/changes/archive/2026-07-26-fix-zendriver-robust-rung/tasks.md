# Tasks

> **FOLDED 2026-07-26 into the `any-browser` promotion** (`shelf-sweep-promotions`
> task 5.2c). §3 (correlated-witness detection) + §4.1 shipped. The blocked §1
> (diagnose CDP handshake) and §2 (fix-or-drop) relocate there: the shelf real-
> launch gate (skip-forbidden) is the container diagnostic that unblocks them.
> The two spec requirements below (distinct evasion engine; observable-not-silent
> fallback) are still true and land on archive.

## 1. Diagnose (blocking — must precede any fix decision)

- [x] 1.1 (FOLDED → any-browser 5.2c) Run `query` against a known hard-anti-bot URL inside the published
      container (or a local Linux container built `--build-arg INSTALL_BROWSER=true`)
      with `debug=true`, forcing browser escalation, and capture the
      `browser_robust` `RenderedPage.detail` — specifically the `_launch_diagnostics`
      suffix that says whether the binary is healthy.
- [x] 1.2 (FOLDED → any-browser 5.2c) If it reports `binary OK … CDP handshake`: capture zendriver's own
      connection error (the module now surfaces it) and the Chromium `--version`
      probe output. Record the exact handshake failure mode.
- [x] 1.3 (FOLDED → any-browser 5.2c) Compare against a patchright render in the same container (which works):
      identify what patchright does at connect time that zendriver does not
      (debug port vs pipe, bind address, user-data-dir/HOME).
- [x] 1.4 (FOLDED → any-browser 5.2c) Write the concrete cause into `LESSONS_LEARNED.md` (replaces the
      "robust rung dead in the image" open note with the root cause).

## 2. Decide + implement (the branch)

- [x] 2.1 (FOLDED → any-browser 5.2c) **If fixable:** apply the launch/connect fix in `zendriver.py`
      (`ZendriverBackend.render`), add a container regression test with the fake
      zendriver asserting the new launch args/config, and verify a real render in
      the container.
- [x] 2.2 (FOLDED → any-browser 5.2c) **If not fixable:** drop the zendriver backend + manifest, and promote
      a distinct second engine for `browser_robust` (a differentiated stealth
      profile of a working backend, or a reinstated Camoufox rung). Ensure it is
      genuinely a different engine/fingerprint than the fast `browser` rung.

## 3. Correlated-witness detection (independent of the branch) — DONE 2026-07-21

- [x] 3.1 `CorrelatedWitnessRung` typed event (`events/types.py`) emitted at WARNING
      from `_escalate_browser` when the robust rung fires with
      `browser_backend_robust == browser_backend`, plus a `correlated_witness` stamp
      on the `browser_robust` diagnostic (the decision-log/debug-surfaced field). The
      detectable revert-trigger for the homelab workaround — a log/operator signal,
      not institutional memory. Tests: `test_correlated_witness.py` (signal fires on
      same-engine, silent on distinct engines).
- [x] 3.2 Corpus entry `hard-anti-bot-robust-escalation` (a DataDome/Cloudflare-hard
      product page) — a same-engine robust rung scores worse (walled) rather than
      passing silently, keeping the escalation path observable.

  Side-fix discovered while tracing the ladder for §3: the released v0.47.0
  `is_complete_small_page` promotion could FALSE-POSITIVE on an under-rendered
  `js_required` SPA (js_required is not hard-wall evidence, so a thin browser regate
  looked like a bare small page). Added `has_shell_fingerprint` (js_required /
  thin_browser_response / empty_result) as a disqualifier for the promotion AND made
  the one-render escalation cap fingerprint-aware so a fingerprinted SPA keeps its
  full fast→robust budget (the distinct robust engine still gets its attempt).

## 4. Gate

- [x] 4.1 `make check` green (§3 + the length_floor side-fix).
- [x] 4.2 (FOLDED → any-browser 5.2c) (DEFERRED with §1-2) `make bench` — run once the robust rung's engine/launch
      is actually changed by the blocked fix; §3 alone did not change render behavior.

## Blocked (needs the container — unchanged)

- Section 1 (diagnose the CDP handshake) and Section 2 (fix-or-drop) remain blocked
  on a diagnostic run inside the published image; cannot be done from a macOS host.
