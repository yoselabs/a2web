# Tasks

## 1. Prove the gap before closing it

- [x] 1.1 Record the baseline probe run verbatim — which handlers pass, which
      fail, and with what. 3/9 red today; the point is that the 6 green ones
      say almost nothing.
- [x] 1.2 Measure each handler on EVERY shape it serves, not just the one in the
      table. Record the observed content length and candidate count per shape —
      those numbers set the floors and are the only defensible basis for them.
- [x] 1.3 Record the twitter `ok`-on-a-wall finding with its captured page, and
      confirm by running `block_detector.evaluate` that the catalogue does not
      fingerprint it.

## 2. The case table

- [x] 2.1 `ProbeCase` dataclass: `url`, `shape`, `min_chars`, `min_candidates`,
      `checks` (prose, required). Frozen, slotted.
- [x] 2.2 Replace `_PROBE_URLS` with `_PROBE_CASES: dict[str, tuple[ProbeCase, ...]]`.
      Keep the existing loud-failure check — a registered handler missing from
      the table fails the probe — and extend it to a handler with an empty tuple.
- [x] 2.3 Floors set BELOW observed values from 1.2, not at them. Write the
      observed value in a comment beside each so the margin is visible and a
      later reader can tell a floor from a golden.
- [x] 2.4 Add the missing shapes: arXiv listing, HN front page, discourse
      listing + topic, reddit listing, wikipedia article. Refresh the stale
      hosts (`linux.do` → `meta.discourse.org`, nitter → the reachable
      instance).
- [x] 2.5 Reddit keeps real floors and stays red (D4). Do not remove it, do not
      lower it. The probe output must name it.

## 3. The assertions

- [x] 3.1 `_probe_one` checks the declared floors and reports observed vs
      declared on failure. "below floor" without the two numbers is not a
      usable failure message.
- [x] 3.2 Probe summary prints the `checks` prose per case, so the run itself
      says what was asserted rather than only whether it held.

## 4. The offline guard (D3)

- [x] 4.1 Test: every registered handler has at least one case.
- [x] 4.2 Test: every handler whose module populates `next_links` has at least
      one case with `min_candidates > 0`. Read the set from the handler sources
      by AST, not from a list — a list is the thing that goes stale.
- [x] 4.3 Test: every case's `checks` is non-empty.
- [x] 4.4 Non-vacuity floors on all three (≥6 handlers walked, ≥5
      candidate-populating). Watch each fail before trusting it.

## 5. The wall fingerprint (D5)

- [x] 5.1 Add the browser-verification pattern to `_BLOCK_PATTERNS`.
- [x] 5.2 Test it against the CAPTURED page, not a hand-written string.
- [x] 5.3 Confirm the existing catalogue tests still pass — a new pattern that
      broadens an existing verdict is a regression risk on legitimate pages.

## 6. Corpus

- [x] 6.1 Entries for `discourse`, `habr`, `twitter`, `v2ex` — the four handlers
      with zero corpus coverage. Criteria phrased against stable structural
      facts, per the standing rule.
- [x] 6.2 Note in the twitter entry that its upstream is currently walled, so a
      failing cell is expected and is information rather than noise.

## 7. Gate

- [x] 7.1 `make check` green, coverage ≥85%.
- [x] 7.2 `make arch` green.
- [x] 7.3 Live probe re-run recorded: what moved from red to green, what stayed
      red, and what NEWLY went red because the assertion got stronger. The last
      of those is the change working.

## 8. Close the loop

- [x] 8.1 BACKLOG: the twitter handler returns `Verdict.ok` on an interstitial.
      The fingerprint fixes the gate's reading; the handler is still lying.
- [x] 8.2 BACKLOG: whether the twitter handler has any reachable upstream at
      all. Three nitter instances tried, all dead or walled.
- [x] 8.3 Mark task 8.6 of `handler-parses-nothing-is-not-success` closed, and
      say which half of wikipedia's guard this actually provides — the live
      half, not a verdict.

## 9. Result

Live probe, 2026-07-28, after: **10/13 cases green** (was "6/9 handlers", which
counted different things — the case count went up because shapes were added).

| case | before | after |
|---|---|---|
| discourse listing | RED (`linux.do` unreachable) | GREEN — 4236 chars, 30 candidates |
| discourse detail | never probed | GREEN — 2649 chars |
| arxiv listing | never probed | GREEN — 4970 chars, 10 candidates |
| hn listing | never probed | GREEN — 6886 chars, 10 candidates |
| reddit ×2 | RED | RED — blocked from this network, declared, kept |
| **twitter** | **would have PASSED** | **RED — 416 chars < 500 floor** |

The twitter row is the change working. With `xcancel.com` configured the old
probe saw `Verdict.ok` and non-empty `content_md` and would have reported it
healthy — while the body was a browser-verification interstitial. The declared
floor is what turns that into a failure.

Nothing regressed: every case green before is green now.
