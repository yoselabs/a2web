# Tasks

## 1. Prove the shadowing bug before fixing it

- [ ] 1.1 Failing test: a failover list of [walled, working] returns the WORKING
      upstream's content, in BOTH orders. Must fail today in the
      walled-first order. This is the claim that outlives the upstream drought
      — write it before the verdict fix, because the verdict fix is what makes
      it pass and they must not be conflated.
- [ ] 1.2 Failing test: a handler fed the captured interstitial does not return
      `Verdict.ok`. Use `tests/fixtures/captured/xcancel_antibot_interstitial.html`,
      already committed — do NOT hand-write an interstitial, for the reason the
      repo adopted the captured-fixture rule.
- [ ] 1.3 Confirm the JSON-API handlers really are immune rather than assumed
      immune: feed one of them an HTML challenge body and record the verdict.
      The proposal claims `json.loads` already fails them; a claim of structural
      immunity is exactly the kind that is worth one run.

## 2. The shared check (D1)

- [ ] 2.1 `handlers/_common.py` gains the challenge helper, beside
      `empty_result` / `map_non_ok`. It consumes
      `packages.block_detector.evaluate`.
- [ ] 2.2 Note in the helper's docstring that this is the FIRST
      `handlers/` → `packages/` import, and that `tach.toml` permits it. A new
      seam edge discovered later reads as an accident.
- [ ] 2.3 Decide and write down what the helper returns: a `TierResult` (like
      `map_non_ok`) or a boolean the caller acts on. The failover loop needs to
      DISTINGUISH "walled, try next" from "walled, give up", so a helper that
      only returns a terminal `TierResult` would not serve it.

## 3. The failover fix (D3 — the half that outlives the drought)

- [ ] 3.1 `_try_instance` classifies its own response and returns a wall verdict
      for a challenge body, so the existing `_NitterInstanceFailure` path
      carries it.
- [ ] 3.2 Confirm the walled instance registers with its circuit breaker —
      that falls out of the existing path but is a behaviour change worth
      asserting, not assuming.
- [ ] 3.3 Exhausted-all terminal: `Verdict.block_page_detected` +
      `try_user_browser_hint(url)`, matching reddit's `_walled_signal` shape.
      Reuse it if it fits; do not fork a second shape.
- [ ] 3.4 Confirm 1.1 passes.

## 4. Apply to the other HTML handlers

- [ ] 4.1 `habr.py` and `wikipedia.py` consult the check. Neither has been
      observed serving a challenge — record that, so the next reader knows these
      are symmetry rather than incident-driven.
- [ ] 4.2 Do NOT apply to the JSON-API handlers, and say why in one line where
      someone would look for it.
- [ ] 4.3 Do NOT touch reddit's existing `_walled_signal` path.

## 5. Gate

- [ ] 5.1 `make check` green, coverage ≥85%.
- [ ] 5.2 `make arch` green; `uv run tach check` clean — the new
      `handlers/` → `packages/` edge must be permitted, not merely unnoticed.
- [ ] 5.3 Every new test watched failing first.

## 6. Evidence

- [ ] 6.1 Re-run the live probe. The twitter case STAYS red — it must, no
      instance works. What changes is the reason: `verdict=block_page_detected`
      rather than `verdict=ok but chars 416 < 500`. Record both lines.
- [ ] 6.2 Re-run the full pipeline on the twitter URL. Confirm `status=failed`,
      `retrieval_incomplete`, critical `try_user_browser` — and confirm it now
      arrives from the HANDLER rather than from the gate's sub-floor branch.
      That is the whole point: remove the dependence on the interstitial being
      short.
- [ ] 6.3 Confirm no other handler's probe case changed. A check applied to
      habr and wikipedia that alters their verdicts would mean a false positive.

## 7. Close the loop

- [ ] 7.1 BACKLOG: remove the two twitter entries this change answers; leave
      the retirement question with its survey date and the condition under which
      it becomes the right call (D4).
- [ ] 7.2 BACKLOG or a follow-up: the wall check at the `SiteHandlerTier` seam
      rather than per handler (design Open Questions). Worth doing when a fourth
      handler needs it, not before.
- [ ] 7.3 Re-survey nitter from a proxied route before any retirement decision.
      One network is one data point.
