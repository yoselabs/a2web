# Thin is not a wall — honest empty-result semantics

## Why

A retrieved HTTP 200 page that renders thin with **no wall evidence** — no
anti-bot markers, not a JS shell, not a blank shell, just under the extraction
length floor — currently terminates as `length_floor` → `wall` → a CRITICAL
`try_user_browser` klaxon ("you are behind an anti-bot wall, you do NOT have this
content"). But that profile is the textbook shape of an **empty search-results
page**: a storefront returns 200 with a styled "no results / Aradığın ürün
bulunamadı / 0 products matched" body that extracts thin. Firing the
maximum-severity anti-bot alarm on a page that is simply *empty* is the exact
cry-wolf ADR-0017 forbids — a confident false "blocked" on zero wall evidence,
which poisons trust in the one klaxon that must always mean something. It is the
still-unfixed sibling of the incehesap-404 incident (`fetch-failure-semantics`);
captured in `eval/corpus.yaml` as `trendyol-200-soft-404-empty-results`.

By the time the terminal classifier sees this, the cascade has *already*
escalated the thin body to a real headless browser (fast Chromium, then robust
CDP) via `playbook.gate_thin_escalate`, and it rendered thin anyway. So this is
not an untested ambiguity — it is a **corroborated thin observation**: a2web ran
the browser and there genuinely is little content. The honest terminal is a
calibrated WARNING that hands the caller the (tiny) body it retrieved, not a
CRITICAL command to open a browser a2web already tried.

## What Changes

- **`length_floor` becomes corroboration-keyed** (mirroring how `not_found`
  already is): a bare thin terminal is a `wall` only when the decision log *also*
  holds hard-wall evidence (`anti_bot` / `block_page_detected` / `paywall` /
  `blank_page`) somewhere — a **whole-log scan**, not the last-gate projection
  (the projection-not-observation trap `terminal.py` was created to fix). A thin
  200 with no hard-wall evidence anywhere becomes a new terminal outcome.
- **New internal `TerminalOutcome.thin_unverified`** (closed enum, not wire): a
  corroborated-thin retrieved page. Maps to a WARNING `content_thin` hint —
  honest about what a2web actually did ("rendered in a headless browser and still
  under the length floor — most likely an empty result set or a minimal page;
  small residual chance of an IP-keyed wall your own browser may differ on").
  NEVER the CRITICAL `try_user_browser`.
- **BREAKING (envelope): attach the thin body to the failure envelope.** On a
  `thin_unverified` `query` result, the retrieved sub-floor body rides the wire
  (a new `thin_content` field on `AskResponse`) even though `query` normally
  withholds content — the body is <500 chars, so it is cheap, and the calling
  agent (which the blind orchestrator serves) can read it and resolve
  empty-vs-wall itself for free. ADR-0015's "never withhold without leaving the
  index," applied to the failure path. Wire-only — a thin/block page NEVER enters
  cache (the never-cache-block-pages invariant is untouched).
- **Do not distill a sub-floor body.** No LLM answer is generated for a
  `thin_unverified` page (already true — extraction runs only on success); the
  raw body is handed over instead. Recorded as an explicit principle so a future
  change does not add a wasteful distill call on a low-prior thin page (ADR-0017).
- `Verdict.other` stays in the wall set (unknown gate failures deserve loud until
  characterized). The block detector, its marker catalogue, and the
  extract-only-on-success guard are untouched.

## Capabilities

### Modified Capabilities
- **retrieval-completeness** — the terminal-story requirements gain the
  `thin_unverified` outcome, the whole-log hard-wall corroboration rule, and the
  thin-body attach. `length_floor` moves out of the unconditional wall set.
- **ask-response** — `AskResponse` gains the conditional `thin_content` field
  (present only on a `thin_unverified` failure).

## Impact

- `src/a2web/actions/terminal.py` — new `thin_unverified` member; whole-log
  hard-wall scan; `length_floor`-as-last-gate → `thin_unverified`.
- `src/a2web/fetcher.py` — `_apply_terminal` maps `thin_unverified`; attach the
  thin body onto the response context.
- `src/a2web/models.py` — `content_thin` hint constructor; `AskResponse`
  `thin_content` field + serializer (omit when absent).
- `src/a2web/fetcher_response.py` — thread the thin body into `build_ask_response`.
- Tests: `tests/capabilities/retrieval_completeness/`,
  `tests/architecture/test_terminal_hint_coherence.py` (new outcome row),
  `tests/capabilities/ask_response/`, `tests/contracts/tool_schemas.json` (re-bless).
- `eval/corpus.yaml` — `trendyol-200-soft-404-empty-results` criteria tightened
  to assert the WARNING + attached body (case already present).
