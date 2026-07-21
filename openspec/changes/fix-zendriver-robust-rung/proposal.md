## Why

The `browser_robust` rung (zendriver over CDP) has never worked in the published
image. `fix(browser): resolve the baked Chromium for zendriver` (df6dab8) fixed
binary *resolution* and made launch failures legible, but did not make the rung
launch. Verified inside the container: with an explicit `browser_executable_path`,
`--no-sandbox`, a writable `user_data_dir`, and `--disable-dev-shm-usage`,
zendriver still reports "Failed to connect to browser", while patchright launches
and renders in the same container as the same uid. So the residual fault is past
process launch — in zendriver's CDP connection handshake — and is zendriver-specific.

This matters beyond one dead rung. `browser_robust` is the *distinct* evasion
engine on escalation: when the fast `browser` rung (patchright) is fingerprinted,
the robust rung is supposed to be a second, independent witness. A same-engine
retry is not independence, and independence is load-bearing — `classify_terminal`
grants `gone_confirmed` only on ≥2 tier agreement, and `is_confirmed_empty`
requires an independent browser render. A silently-degraded robust rung tilts the
empty-vs-wall false-positive asymmetry the wrong way without announcing it.

The homelab deployment currently works around this by pointing `browser_robust`
at patchright (a correlated witness). That workaround must be reverted the moment
a genuinely distinct engine works — but nothing today makes that condition
*detectable*; it depends on someone recalling the decision.

## What Changes

- **Diagnose the CDP handshake failure first — this change is diagnose-then-fix,
  not fix-blind.** df6dab8 added `_launch_diagnostics` that already distinguishes
  "binary is healthy, handshake failed" from "binary is broken". Capture the
  handshake failure from inside the target container (the `binary OK: … failure
  is in the CDP handshake` path) and record the concrete cause before choosing a
  remedy. Candidate causes to rule in/out: CDP websocket bind address vs the
  container's loopback, `--remote-debugging-port` vs `--remote-debugging-pipe`,
  the user-data-dir / `HOME` writability zendriver assumes, and zendriver's
  connection-handshake timing against a cold Chromium.

- **Then EITHER fix the launch OR drop zendriver and promote a working robust
  rung.** Decision is an *output* of the diagnosis, not an input. If zendriver's
  handshake is fixable with launch flags a2web controls, fix it. If it is not
  (upstream defect, unmaintained), drop the zendriver backend and make the second
  escalation engine a distinct *stealth* configuration of a working backend
  (patchright with a different fingerprint profile, or a reinstated Camoufox
  rung) so `browser_robust` is genuinely independent of `browser`, not a rename.

- **Make same-engine degradation detectable.** Whatever the robust rung resolves
  to, emit a signal when it resolves to the *same engine* as the fast rung, so a
  correlated-witness fallback (the current homelab workaround, or a future
  regression) is visible rather than silent. This is the trigger the revert
  condition needs: an operator/log signal, not institutional memory.

- **Correct the record.** The zendriver manifest's claim that it has "no inherited
  stderr to capture" was already corrected in df6dab8; this change closes the loop
  by recording the real CDP-handshake cause in `LESSONS_LEARNED.md` so the next
  reader does not re-derive it.

## Impact

- Affected code: `src/a2web/packages/browser_backends/zendriver.py`, the
  `_manifests/browser_backends/` robust-rung wiring, `src/a2web/tiers/browser.py`
  (the `browser_robust` name + operator hint), and possibly a reinstated backend
  manifest if zendriver is dropped.
- Affected behavior: hard anti-bot sites gain a genuine robust retry; the
  correlated-witness degradation becomes observable.
- Blocked on: a diagnostic run inside the published container (or an equivalent
  Linux container built with `INSTALL_BROWSER=true`). Cannot be completed from a
  macOS dev host alone, because the failure is container-specific.
- Not breaking: no response-envelope or tool-signature change.
