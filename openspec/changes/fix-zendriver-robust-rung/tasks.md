# Tasks

## 1. Diagnose (blocking — must precede any fix decision)

- [ ] 1.1 Run `query` against a known hard-anti-bot URL inside the published
      container (or a local Linux container built `--build-arg INSTALL_BROWSER=true`)
      with `debug=true`, forcing browser escalation, and capture the
      `browser_robust` `RenderedPage.detail` — specifically the `_launch_diagnostics`
      suffix that says whether the binary is healthy.
- [ ] 1.2 If it reports `binary OK … CDP handshake`: capture zendriver's own
      connection error (the module now surfaces it) and the Chromium `--version`
      probe output. Record the exact handshake failure mode.
- [ ] 1.3 Compare against a patchright render in the same container (which works):
      identify what patchright does at connect time that zendriver does not
      (debug port vs pipe, bind address, user-data-dir/HOME).
- [ ] 1.4 Write the concrete cause into `LESSONS_LEARNED.md` (replaces the
      "robust rung dead in the image" open note with the root cause).

## 2. Decide + implement (the branch)

- [ ] 2.1 **If fixable:** apply the launch/connect fix in `zendriver.py`
      (`ZendriverBackend.render`), add a container regression test with the fake
      zendriver asserting the new launch args/config, and verify a real render in
      the container.
- [ ] 2.2 **If not fixable:** drop the zendriver backend + manifest, and promote
      a distinct second engine for `browser_robust` (a differentiated stealth
      profile of a working backend, or a reinstated Camoufox rung). Ensure it is
      genuinely a different engine/fingerprint than the fast `browser` rung.

## 3. Correlated-witness detection (independent of the branch)

- [ ] 3.1 Emit a signal (log event + a `TierResult`/decision-log field) when the
      resolved `browser_robust` engine equals the resolved `browser` engine, so a
      same-engine fallback is observable. This is the detectable revert-trigger
      for the homelab workaround.
- [ ] 3.2 Add a corpus entry (`eval/corpus.yaml`) for the hard-anti-bot
      escalation path so a same-engine robust rung shows up as degraded scoring
      rather than silence (the `affordance`/escalation class).

## 4. Gate

- [ ] 4.1 `make check` green.
- [ ] 4.2 If the robust rung changed engines or launch behavior, run `make bench`
      (live-network) to confirm anti-bot escalation quality did not regress.
