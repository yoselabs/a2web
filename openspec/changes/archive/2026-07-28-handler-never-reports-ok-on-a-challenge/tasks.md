# Tasks

## 1. Prove the shadowing bug before fixing it

- [x] 1.1 Failing test: a failover list of [walled, working] returns the WORKING
      upstream's content, in BOTH orders. Must fail today in the
      walled-first order. This is the claim that outlives the upstream drought
      — write it before the verdict fix, because the verdict fix is what makes
      it pass and they must not be conflated.
- [x] 1.2 Failing test: a handler fed the captured interstitial does not return
      `Verdict.ok`. Use `tests/fixtures/captured/xcancel_antibot_interstitial.html`,
      already committed — do NOT hand-write an interstitial, for the reason the
      repo adopted the captured-fixture rule.
- [x] 1.3 Confirm the JSON-API handlers really are immune rather than assumed
      immune: feed one of them an HTML challenge body and record the verdict.
      The proposal claims `json.loads` already fails them; a claim of structural
      immunity is exactly the kind that is worth one run.

## 2. The shared check (D1)

- [x] 2.1 `handlers/_common.py` gains the challenge helper, beside
      `empty_result` / `map_non_ok`. It consumes
      `packages.block_detector.evaluate`.
- [x] 2.2 Note in the helper's docstring that this is the FIRST
      `handlers/` → `packages/` import, and that `tach.toml` permits it. A new
      seam edge discovered later reads as an accident.
- [x] 2.3 DECIDED: `Verdict | None`. A terminal `TierResult` cannot serve the
      failover loop — only the CALLER knows whether untried upstreams remain.
      Written into the helper's docstring.
- [x] 2.4 REVISED ON EVIDENCE (D1b): the helper takes the REAL `content_md`, not
      `""`. Forcing the catalogue's length-gated markers on turned the wikipedia
      Python article into `block_page_detected` on a cited PEP title containing
      "Network Security". Regression-tested both ways:
      `test_challenge_check_does_not_fire_on_an_article_quoting_a_wall_phrase`
      and `..._still_fires_on_a_vendor_fingerprint_at_any_length`.
- [x] 2.5 The header is given NO vote (`content_type=None`). `evaluate` would
      short-circuit a non-HTML content-type to `content_type_mismatch`, which
      here would let a wall labelled `application/json` switch off its own
      detection. Found because `FakeCurlResp` defaults to `application/json`.

## 3. The failover fix (D3 — the half that outlives the drought)

- [x] 3.1 `_try_instance` classifies its own response and returns a wall verdict
      for a challenge body, so the existing `_NitterInstanceFailure` path
      carries it.
- [x] 3.2 Confirm the walled instance registers with its circuit breaker —
      that falls out of the existing path but is a behaviour change worth
      asserting, not assuming.
- [x] 3.3 Exhausted-all terminal: `Verdict.block_page_detected`. Reddit's shape
      was evaluated as instructed and DOES NOT FIT — the eager
      `try_user_browser_hint` is deliberately NOT carried. Live: nitter walled →
      hint attached → jina then retrieved the tweet, leaving a critical "this URL
      was NOT retrieved" on a response holding 2204 chars of it.
      `_attach_failure_floor` owns the hint and stands down on `ok`. See D3.
- [x] 3.4 Confirm 1.1 passes.

## 4. Apply to the other HTML handlers

- [x] 4.1 `wikipedia.py` consults the check — symmetry, not incident, recorded
      inline. `habr.py` does NOT: the audit listed it as an HTML handler AND as a
      JSON-API one; it is JSON-only (`isinstance(payload, dict)`), so it is
      structurally immune. Proposal corrected.
- [x] 4.2 Not applied to the JSON-API handlers; the reason lives in the test
      that proves the immunity, which is where someone checking would look.
- [x] 4.3 Do NOT touch reddit's existing `_walled_signal` path.

## 5. Gate

- [x] 5.1 `make check` green, coverage ≥85%.
- [x] 5.2 `make arch` green; `uv run tach check` clean — the new
      `handlers/` → `packages/` edge must be permitted, not merely unnoticed.
- [x] 5.3 Every new test watched failing first.

## 6. Evidence

- [x] 6.1 Live probe re-run. Twitter stays red, for the new reason:
        before: `[FAIL] twitter  verdict=ok but chars 416 < 500`
        after:  `[FAIL] twitter  verdict=block_page_detected (1037ms)`
- [x] 6.2 Full pipeline re-run — and the predicted outcome was WRONG, which is
      how the eager-hint defect was found. With a nitter instance configured the
      cascade does NOT fail: handler `block_page_detected` → raw 404 → browser
      timeout → JINA OK (2204 chars) → `status=ok`,
      `retrieval_incomplete=False`. That is correct: the URL WAS retrieved, so
      ADR-0009's failure treatment must not fire. What the run caught was the
      handler's eager critical hint riding along on that success (task 3.3).
      Confirmed after the fix: `status ok`, no `try_user_browser` hint, and the
      handler's wall still recorded as an observation at `t_ms=0`.
      The wall verdict does now arrive from the HANDLER, not the gate's
      sub-floor branch — the original point of the task.
- [x] 6.3 This check DID catch a false positive, exactly as feared — wikipedia
      went red on the first run. Root-caused, fixed (D1b), and wikipedia is back
      to `ok (49120 chars, 10 candidates)`. All other cases unchanged; the
      remaining reds (reddit ×2, arxiv detail) are the pre-existing
      rate_limited/timeout ones that need a proxy.

## 7. Close the loop

- [x] 7.1 BACKLOG: remove the two twitter entries this change answers; leave
      the retirement question with its survey date and the condition under which
      it becomes the right call (D4).
- [x] 7.2 BACKLOG or a follow-up: the wall check at the `SiteHandlerTier` seam
      rather than per handler (design Open Questions). Worth doing when a fourth
      handler needs it, not before.
- [x] 7.3 Re-survey nitter from a proxied route before any retirement decision.
      One network is one data point.
