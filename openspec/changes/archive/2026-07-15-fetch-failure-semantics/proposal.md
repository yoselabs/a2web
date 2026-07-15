## Why

A live fetch of a dead storefront **search URL** returned `status: failed, tier: jina, verdict: length_floor` plus a **CRITICAL** `try_user_browser` hint ("behind an anti-bot wall, you do NOT have this content"). The URL was a genuine **HTTP 404**. Three tiers saw it — `raw → 404`, our own `browser → 404`, `jina → 200` wrapping `"Target URL returned error 404"` — yet the caller was told it was walled and *commanded* to spend a browser session on a page that does not exist. Because the hint is an instruction injected into another agent's context (agents obey CRITICAL), a miscalibrated severity here does not merely annoy — it corrupts downstream agent behavior.

Root cause is two structural bugs, not a missing regex:

1. **Tiers lie about their outcome.** A tier that retrieves an *error page* launders it into `ok`: `jina` wraps an upstream 404 as its own HTTP 200; the `browser` tier renders the 404 page and reports `ok` (bytes came back) with the real 404 buried in a diagnostic. The decision log — the system's stated source of truth — then holds a **false observation**, and every downstream layer reasons on poison.
2. **The terminal classifier reads a projection, not the evidence.** `_is_genuine_gone()` keys on `fc.resolved_verdict()` (here `length_floor`, from jina's poisoned win) and so cannot see the two independent `404` observations already in the log. This bug **survives** fixing jina — any future mis-winning tier reproduces it.

Compounding this, the "what does a failure MEAN / what do we tell the caller" policy is smeared across six files (`block_detector`, `fetcher.evaluate`, `playbook`, `_is_genuine_gone`, `_prescribe_browser_on_wall`, handlers), and the caller reads three overlapping classification channels (`Verdict`, `Obstacle`, `OperatorHint`+`severity`) with no declared consistency relation — which is exactly how `length_floor` + `try_user_browser` shipped on `not_found` evidence.

## What Changes

- **A tier-truthfulness contract.** A tier that retrieves an error page SHALL surface the real upstream status on its `TierResult`, never launder it into `ok`. `jina` unwraps its own reader stub — generalized `Target URL returned error (\d{3})` → the existing `_verdict_for_status` (not enum-by-enum; the current `40[13]` already missed 404 once and would miss 410/429/500 next). The `browser` tier surfaces a retrieved error-page status. Once tiers are truthful, the decision log holds `raw:404, jina:404, browser:404` and corroboration is *observable*.
- **Delete the gate's jina-stub special-case.** With unwrap at the tier, `fetcher.evaluate()`'s `_JINA_PAYWALL_STUB_RE` branch and its two module constants are removed — one of four gate special-cases dies, and the `tier == "jina"` guard (the confession that it was mis-layered) goes with it. The wrapped-401/403 → `paywall` → archive routing is **preserved** by mapping those two statuses to `Verdict.paywall` inside the jina unwrap (behaviour-neutral except the 404 we are fixing).
- **`classify_terminal(observations, resolved_verdict) -> TerminalOutcome`** — one pure, closed-enum classifier reading the **decision log**, replacing `_is_genuine_gone` + `_prescribe_browser_on_wall`. It is the backward-looking sibling of the `playbook` (playbook = forward "next action"; this = terminal "story"): same substrate, same purity, same test style. It structurally fixes bug #2 and is where the 404 flavors live.
- **Corroboration-keyed `not_found` semantics** (the third not-found state):
  - handler-authoritative gone → silent (unchanged);
  - HTTP 404 that our **browser corroborated** (also 404) → `gone_confirmed`: "not found — likely a dead/wrong URL, confirmed by a rendered browser", **INFO**, no `try_user_browser`, no soft-404 caveat;
  - HTTP 404 whose soft-404 check **could not run** (browser budget spent / pool unavailable / browser saw something else) → `gone_unverified`: "likely a dead URL; **small** chance a bot-defense soft-404 is masking real content; open it in your own browser if you truly need it", **WARNING**.
  - Severity thus **encodes confidence, and confidence comes from corroboration** — which structurally prevents the cry-wolf a "caveat on every 404" would train.
- **`warning` severity** added to `OperatorHint.severity` (today `info | critical`). The **only** wire change.
- **Incoming reader-prefix normalization.** When a caller passes an already-wrapped reader URL (`https://r.jina.ai/<real-url>`), the `fetch()` entrypoint SHALL strip the prefix and fetch `<real-url>` with a2web's own ladder — sibling to the existing captcha-host rewrite. A pre-wrapped URL otherwise pins a2web to jina with **no** raw/browser/paid fallback (it treats `r.jina.ai` as the origin); the calling agent must never have to pre-wrap, and doing so must not disable recovery.
- **Corpus + replay** (house rule "never lose a case"): the Turkish 404 as a decision-log replay of the exact `raw:404 → jina-wrapped-404 → browser:404` sequence, plus the **200-soft-404 sibling** (storefronts that return HTTP **200** + a "no results" body — the same false klaxon with zero status evidence; captured now, narrative hedged, fix deferred).
- **ADR + a taxonomy consistency arch-test.** An ADR states the law (*escalation effort ∝ prior that content exists; terminal confidence ∝ corroboration; hint severity encodes confidence*). A new `tests/architecture/` test asserts a declared coherence table over `(verdict × obstacle × hint-code)` on the response builder — it would have caught this incident's class (`length_floor` + `try_user_browser` on `not_found` evidence).

Explicitly **not** in scope (leave alone): `playbook.py` (the rule table is sound), `block_detector.py` (empirical, pure, do-not-weaken), the surviving `evaluate()` exemptions (js-heavy / JSON / structured-answer — genuinely gate-domain), collapsing `Verdict`/`Obstacle` (different layers, producers, and reliability — `Obstacle` is a Literal-4 *because* LLMs are unreliable at wide classification; it is an independent second witness, not redundancy), and any *general* cross-tier corroboration engine (rule-of-three: one use case → one arm of `classify_terminal`, not infrastructure).

## Capabilities

### New Capabilities
<!-- none — this refines existing capabilities -->

### Modified Capabilities

- `retrieval-completeness`: the never-silently-miss floor is re-expressed as the output of a single pure `classify_terminal` reading the observation log (not a whitelist over the resolved verdict). `not_found` gains the corroboration-keyed `gone_confirmed` / `gone_unverified` split; the critical `try_user_browser` is scoped to genuine walls; `severity` gains a confidence semantics (`info` = verified fact, `warning` = could-not-finish-checking, `critical` = tried-everything-hit-a-wall).
- `tier-pipeline`: a new **tier-truthfulness** requirement (a retrieved error page surfaces its upstream status, never `ok`); jina unwraps its own reader stub; a new **incoming reader-prefix normalization** at the `fetch()` entrypoint.
- `quality-gate`: the jina-stub body-regex special-case is REMOVED from `evaluate()` (moved to the jina tier); the gate no longer branches on `tier == "jina"`.

## Impact

- `src/a2web/tiers/jina.py` — unwrap the reader stub: generalized `(\d{3})` capture → `_verdict_for_status`, real `status_code`, `pre_rendered=None` on a wrapped error; wrapped 401/403 → `Verdict.paywall` to preserve archive routing. Keep the body-length guard so an article quoting the stub string cannot false-positive.
- `src/a2web/tiers/browser.py` — surface a retrieved error-page status on `TierResult` so a browser-confirmed 404 is an observation, not a buried diagnostic.
- `src/a2web/fetcher.py` — remove `_JINA_PAYWALL_STUB_RE` + `_JINA_STUB_MAX_BODY` and the `tier == "jina"` gate branch; replace `_is_genuine_gone` + `_prescribe_browser_on_wall` with a call to `classify_terminal`; add the incoming reader-prefix strip beside `rewrite_captcha_host` at the `fetch()` entrypoint.
- `src/a2web/actions/terminal.py` (new) — `classify_terminal(observations, resolved_verdict) -> TerminalOutcome`, pure, closed-enum, sibling to `playbook.py`.
- `src/a2web/models.py` — `OperatorHint.severity` gains `warning`; a `content_not_found` hint constructor; `try_user_browser` scoped away from `not_found`.
- `eval/corpus.yaml` + `eval/corpus/regression/` — the 404 replay case + the 200-soft-404 sibling.
- `tests/architecture/` — the `(verdict × obstacle × hint-code)` coherence test.
- `openspec` / `docs` — the ADR.
- **Wire contract**: the ONLY change is the new `warning` value on `OperatorHint.severity`; verify the installed MCP client tolerates an unknown severity before shipping (Ask-First: response-envelope shape). No `query`/`fetch_raw` field is added or removed; `Obstacle` is untouched.
- Invariants preserved: decision log stays the pure source of truth; block-pages-never-cached; browser cap (2, fast→robust) and paid cap (1); ADR-0009 loud incompleteness (now *more* honest, not less).
