# Design — empty-vs-wall-discrimination

## The reducibility argument (why this is not "manufacturing a verdict")

The worry that any discriminator is a2web inventing certainty it lacks (an
ADR-0012-flavored sin) misfires. ADR-0012 bans manufacturing a *selection* —
ranking by a criterion a2web does not own. Classifying an observation with
disclosed confidence is ADR-0017's job, and ADR-0017 already *licenses* confirmed
verdicts from corroboration: `gone_confirmed` is crowned from two independent
404s. `empty_confirmed` is the twin, built from the same evidence structure.
Refusing it would be applying the doctrine to one verdict class and not its
mirror. The residual does not go to zero (deliberate cloaking guarantees a floor),
but it is reducible the same way the 404 problem was.

## The false-positive asymmetry (the center of gravity)

```
                    false-positive WALL            false-positive EMPTY
 what happens       over-warn; caller opens        promote a real wall to
                    their browser                  ok: "no results found"
 cost               mild waste (one browser)       CONFIDENT SILENT MISS —
                                                   terminates the caller's
                                                   search plan; propagates
                                                   ("this product doesn't exist")
 direction          the cheap, safe direction      the catastrophic direction
                                                   (the ADR-0009 harm itself)
```

Every design choice below points the residual error toward the wall side. The
empty→ok promotion is guarded by a conjunction; anything short of it stays a
loud-ish `failed`.

## Why the discriminator is NOT in the body text

Two real cases defeat *any* text reader — regex (Opt 1) OR LLM (Opt 2):

1. **The walled-API fake-empty.** SPA storefront: HTML shell 200s and renders;
   the product-search XHR is 403'd by the WAF; the page renders its own
   *authentic* "0 results" template, in the site's language, pixel-identical to a
   true empty. No wall text exists. Text classification confidently says `empty`.
   This is the *default* architecture of modern storefronts, not an edge case.
2. **Cloaking.** Bot-mitigation vendors increasingly serve deceptive clean 200s
   (fake-empty results) to suspected bots to poison scrapers quietly. A text→ok
   promotion is an amplifier for exactly this. The adversary controls the text
   (ADR-0014: attacker-controlled labels — same doctrine applies to body text).

The only signal that separates the walled-API fake-empty from a true empty is
non-text: **the browser watched the XHR get 403'd.** Today that observation dies
inside Camoufox. Surfacing it is the real reducibility lever, and it fits the
architecture exactly — tier work feeding the pure classifier, like jina's
error-stub decoding is tier work, not gate work.

## Why not a regex empty-catalogue as a promotion authority (false symmetry)

`_BLOCK_PATTERNS` works because the wall space *converges*: ~6 mitigation vendors
produce recognizable fingerprints. An empty-result catalogue never converges:
millions of sites each phrase "no results" differently, across every language.
Maintaining `_EMPTY_RESULT_PATTERNS` as the thing that flips `failed→ok` is
permanent whack-a-mole AND cloaking-food. So the empty-marker is used ONLY to
(a) sharpen `thin_unverified`→`empty_unverified` wording and (b) be ONE necessary
term in the promotion conjunction — never sufficient, never the authority.

## Why not an LLM as the promotion authority

The purity objection (an LLM read would break `classify_terminal`) does not hold
— an LLM label could be tier-side work emitting an observation, structurally like
jina decoding. The correct reason it loses: the LLM reads the SAME
attacker-controlled text the regex reads, so against the walled-API fake-empty and
cloaking it is exactly as blind, with worse determinism. LLM label as one
observation among several — maybe, later; LLM as the `failed→ok` flip — never.
(On the `query` path the extractor already reads the body, so an "empty" signal
is nearly free there — deferred; the conjunction does not need it.)

## Seams

`classify_terminal` is called ONLY on a failed fetch — `TerminalOutcome` is a
failure taxonomy. So an `ok` empty must be decided BEFORE it, at the orchestrator's
verdict-handling phase, via a pure predicate:

```
_run_pipeline
  └─ resolve_verdict(log) -> Verdict           # unchanged, pure
  └─ if verdict != ok:
       if is_confirmed_empty(log, url):        # NEW pure predicate (actions/empty.py)
           -> promote to ok: synthetic "no results" answer, body attached, NO cache
       else:
           classify_terminal(log, verdict)     # extended: subresource->wall, empty_unverified
```

`is_confirmed_empty(observations, url) -> bool` — pure, total, no I/O; the
promotion conjunction, testable exactly like `classify_terminal`. Kept a separate
predicate (not folded into a Verdict rank) so the risky `→ok` flip lives in one
auditable place and resolve_verdict stays simple.

### The promotion conjunction (all must hold)

1. an independent BROWSER render read the page as empty too — a regate gate outcome
   (`source="regate"`) carrying the empty marker (`subsystem="empty_result"`);
2. an HTTP `tier_outcome` returned a body (`verdict == ok`);
3. NO observation with `status_code` in {401, 403, 429} anywhere;
4. NO subresource-block evidence anywhere (`subresource_blocks == 0` on every obs);
5. NO hard-wall gate evidence anywhere (reuses `has_hard_wall_evidence`);
6. the URL is search-shaped (`is_search_shaped(url)` — a query param or a
   `/search|/arama|/sr|…` path). An "empty" reading of a non-search route is
   itself suspicious.

**Corroboration is by the browser, not jina (implementation-revealed correction).**
The original design assumed jina (foreign egress) corroborates the empty. But a
thin HTTP 200 WINS the tier loop — raw returned `ok`, so the free jina rung never
runs on it (jina only runs when raw fails outright). The second independent
retrieval a thin page actually gets is the planner's browser escalation
(`_decide_gate_thin_escalate` routes `length_floor` → browser). That is the
stronger corroborator here anyway: a real anti-detect browser renders the page AND
watches every subresource (term 4), so a walled-API fake-empty cannot pass. The
residual (an IP-reputation wall that fake-empties our HTTP AND browser egress
identically) is narrow; the attached `thin_content` is its mitigation. Cost: a
deployment with no browser backend never promotes — the conservative fallback.

### `classify_terminal` extensions (failure path)

- **subresource-block evidence anywhere → `wall`** (new, ranked ABOVE the thin
  branch and even above corroborated-404: a browser that watched an XHR get
  challenged is positive wall evidence). This is the walled-API fake-empty catch.
- **empty-marker present but not promoted → `empty_unverified`** — a leaning-empty
  cousin of `thin_unverified`: still `failed`, `content_thin` WARNING, but the
  wording may lean empty ("the page reads as an empty result set but corroboration
  was incomplete"). No new hint code — reuse `content_thin` (severity warning).
- **no marker, no wall evidence → `thin_unverified`** (unchanged) — now with Opt-0
  agnostic wording.

## Observation & backend plumbing (C)

- `RenderedPage` (browser-backend, domain-free) gains `subresource_blocks: int = 0`.
- `PlaywrightBackend.render` attaches `page.on("response", …)` before `goto`,
  counting responses whose `request.resource_type in {"xhr","fetch"}` and
  `status in {401,403,429}`. Bounded, cheap, best-effort (never raises).
- The browser `TierResult` gains `subresource_blocks: int = 0` (typed field, no
  `tier_extras` bag — the invariant holds).
- `Observation` gains `subresource_blocks: int = 0` (sits beside `status_code` /
  `cloudflare` as planner/classifier evidence). The fetcher copies it from the
  browser `TierResult` when appending the browser tier_outcome.

## Cache policy (D)

A promoted `ok` empty MUST NOT enter cache (or a very short TTL) — empties churn,
and a wrongly-promoted empty entering cache converts one silent miss into a
served-from-cache *repeating* silent miss. The promotion path marks the response
no-cache, alongside the existing never-cache-block-pages guard.

## Consciously deferred

- LLM empty-signal from the existing `query` extraction call (nearly free) as a
  further conjunction term — not needed for a conservative promotion; revisit if
  jina-required corroboration proves too strict in bench.
- Consent/GDPR interstitials ("we value your privacy") render thin with benign
  text matching neither catalogue — a distinct third residual class. They stay
  `thin_unverified` (correctly: passable, content behind consent). Not chased here.
