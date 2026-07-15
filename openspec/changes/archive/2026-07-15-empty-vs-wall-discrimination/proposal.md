# Proposal — empty-vs-wall-discrimination

## Why

The thin-not-wall change (shipped) stopped a thin retrieved 200 from firing the
critical anti-bot klaxon: a sub-floor body with no hard-wall evidence now
resolves `thin_unverified` (a WARNING + the body attached). That fixed the
cry-wolf, but it left ONE residual bucket — "bare `length_floor`" — structurally
ambiguous between two things that must not be conflated:

- a genuine **empty result** ("0 products", "no matches") — content legitimately
  absent, where "no results" IS the complete, correct answer; and
- a **bespoke wall** whose interstitial text is not in `_BLOCK_PATTERNS` (a
  PerimeterX "Pardon the interruption" / bare "Access Denied"), OR the nastier
  **walled-API fake-empty**: an SPA shell 200s and renders its own authentic
  "0 results" template because the product-search XHR behind it was 403'd by the
  WAF. Content EXISTS; we are being blocked; no wall text is on the page.

Two harms live here. (1) A real wall gets the soft `thin_unverified` hedge — and
the current `content_thin` wording *asserts* "most likely an empty result set",
actively misleading when it is a wall (an ADR-0009 cry-wolf in reverse:
under-warning a wall). (2) A genuine empty is a complete answer but we return
`status: failed`, never `ok`.

These are the two error-directions of one missing capability: discriminate
empty from wall. The discriminator is NOT in the body text — a regex catalogue
and an LLM read are equally blind to the walled-API fake-empty and are amplifiers
for deliberate cloaking (attacker-controlled text; cf. ADR-0014). The reducible
signal is **evidence**: cross-egress corroboration (already how 404 works) plus a
non-text observation the browser tier alone can see — subresource (XHR/fetch)
challenge statuses during render.

The false-positive asymmetry is the design's center of gravity: a false-positive
wall over-warns (caller opens their browser — cheap). A false-positive empty
promotes a real wall to `ok: "no results"` — a confident SILENT MISS that
terminates the caller's search plan ("this doesn't exist"), the exact ADR-0009
harm the system exists to prevent. So text alone never says `ok`; promotion
requires a hard corroboration conjunction that includes the subresource evidence.

## What changes

Staged A→D so it can land incrementally; D is the only breaking flip.

- **A · Honest wording (non-breaking).** Reword the `content_thin` hint and the
  `thin_unverified` docstring to drop the "most likely an empty result set"
  base-rate assertion → symmetric: "thin — could be an empty result OR an
  unfingerprinted wall; body attached, you judge."
- **B · Extend the WALL catalogue (non-breaking).** Add bounded, high-precision
  bespoke-wall phrases to `_BLOCK_PATTERNS` (PerimeterX, "Access Denied",
  "Request unsuccessful"). Shrinks the residual from the wall side; a
  false-positive here only over-warns. (The wall catalogue converges — ~6
  mitigation vendors; the empty catalogue never would, so we do NOT build its
  twin as a promotion authority.)
- **C · Subresource-block evidence (non-breaking, new observation).** The browser
  backend counts XHR/fetch responses with challenge statuses (401/403/429)
  during render and surfaces `RenderedPage.subresource_blocks`; the browser tier
  carries it onto `TierResult` and the fetcher records it on the browser
  `Observation`. `classify_terminal` treats subresource-block evidence anywhere
  in the log as a **`wall`** — catching the walled-API fake-empty that no text
  reader can. Also adds a conservative empty-marker gate annotation
  (`_EMPTY_RESULT_PATTERNS` → a `subsystem="empty_result"` tag on the thin gate),
  which sharpens `thin_unverified` into `empty_unverified` (leaning-empty
  WARNING) when present — still `failed`, never promoted on its own.
- **D · The endgame — corroborated empty → `ok` (BREAKING: a `failed→ok` flip for
  a page class; envelope semantics — Ask First, authorized).** A pure predicate
  `is_confirmed_empty(observations, url)` promotes to `ok` ONLY under the full
  conjunction: an independent browser render read the page empty too (a regate
  carrying the empty marker) AND an HTTP tier returned a body AND zero
  4xx/challenge status anywhere AND zero subresource-block evidence AND no
  hard-wall gate evidence AND a search-shaped URL. (Corroboration is by the
  browser, not jina — a thin 200 wins the tier loop, so jina never runs on it;
  the browser escalation is the second independent retrieval, and it also watches
  subresources.) On promotion the `query` answer is a synthetic
  honest "the page reports no results" at `confidence: low` with the body still
  attached; the promoted empty is wire-only and NEVER cached (a wrongly-cached
  empty is a repeating silent miss).

## Impact

- Affected specs: `retrieval-completeness` (terminal story + empty outcomes),
  `quality-gate` (empty-marker + wall-catalogue), `browser-backend` (subresource
  capture), `ask-response` (the `ok`-empty answer shape).
- Affected code: `packages/block_detector.py`, `packages/browser_backends/{base,playwright}.py`,
  `tiers/browser.py`, `tiers/__init__.py` (`TierResult`), `decision_log.py`
  (`Observation` evidence field), `actions/terminal.py` (subresource→wall,
  `empty_unverified`), a new pure `actions/empty.py` (`is_confirmed_empty`),
  `fetcher.py` (promotion phase + evidence plumbing), `fetcher_response.py`
  (empty answer + no-cache), `models.py` (hint wording + `content_empty` hint),
  `domain.py` (`is_search_shaped`).
- **D is a breaking envelope change** (a class of URL that returned `failed` now
  returns `ok`). Contract re-bless required; corpus cases updated.
- Corpus (same session, repo rule): a bespoke-wall thin 200 (PerimeterX), a
  genuine TR 0-result storefront search, and — if a live one is found — an SPA
  whose search API is easily walled (the fake-empty).
