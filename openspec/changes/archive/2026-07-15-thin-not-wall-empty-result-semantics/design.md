# Design — thin-not-wall-empty-result-semantics

## Context

Pressure-tested with the Fable council (2026-07-16). Two premise corrections
reshaped the design; recorded here so they are not re-litigated.

## Decision 1 — `length_floor` is corroboration-keyed via a WHOLE-LOG scan

`classify_terminal` must NOT key the thin-vs-wall decision on `_last_gate_verdict`
alone. Counter-case: an early `anti_bot` (Turnstile marker) → browser dispatched
→ browser lands on a bespoke marker-less thin stub (challenge unsolved) → regate =
`length_floor`. The *last* gate is now `length_floor`, but the log holds positive
Turnstile evidence — this is a real wall and must stay CRITICAL. Keying on the
last gate would downgrade it to WARNING, re-committing the exact
projection-not-observation sin this module was built to fix (the `_is_genuine_gone`
failure).

**Rule:** `thin_unverified` fires only when the last gate outcome is
`length_floor` AND **no** gate observation *anywhere* in the log carries a
hard-wall verdict (`anti_bot`, `block_page_detected`, `paywall`, `blank_page`).
A hard-wall verdict anywhere → `wall`.

Precedence in `classify_terminal` (top wins):
1. `paid_auth_error` → `operator_error`
2. `dns_error` / `content_type_mismatch` → `unreachable`
3. authoritative `not_found` → `gone_confirmed`
4. **hard-wall evidence anywhere in the log → `wall`** (whole-log scan)
5. ≥2 corroborated `not_found` → `gone_confirmed`
6. lone `not_found` → `gone_unverified`
7. **last gate == `length_floor` → `thin_unverified`** (a body was retrieved and
   rendered thin; no hard-wall, no not_found)
8. else → `wall` (the default floor: bodyless transport failures — `timeout`,
   `connection_error`, `proxy_unavailable` — where a browser might still get
   through; and `Verdict.other`, kept loud until characterized)

`_HARD_WALL_GATE_VERDICTS = {block_page_detected, anti_bot, paywall, blank_page}`
is a NEW frozenset scanned across the whole log. `_WALL_GATE_VERDICTS` (the old
last-gate set that included `length_floor` and `other`) is removed — `length_floor`
now routes to step 7, `other` falls to the step-8 default.

Why this is not under-warning: by step 7 the cascade has run raw → jina → browser
(fast) → browser (robust) and all rendered thin (`gate_thin_escalate`). The
"needs a real browser" hypothesis was actively tested twice and failed. The one
residual real class — IP-reputation walls serving bespoke thin 200s in an
un-catalogued language, where a2web's browser egresses through the same IP — is
knowingly downgraded CRITICAL→WARNING. Accepted because (a) the WARNING keeps the
browser escape hatch, and (b) Decision 2 lets the caller tell the difference
itself. A confident false "you are blocked" on every empty storefront search is
worse than this residual: it poisons the klaxon that must mean something.

## Decision 2 — attach the thin body to the failure envelope (the load-bearing piece)

Without the body, a `thin_unverified` WARNING is a warning the blind caller
cannot act on — noise that trains agents to ignore warnings (cry-wolf one level
down). The retrieved body is <500 chars — the *entire* content, tiny. Attach it:
the calling agent reads the language a2web's regexes cannot, sees "no results,"
and resolves empty-vs-wall for free — zero LLM, zero network, zero new fetch.
This is ADR-0015 ("never withhold without leaving the index") on the failure
path, and it makes Option C (spend an LLM to emit an `Obstacle`) dead weight: the
caller does that classification better, for free, knowing its own question.

- `AskResponse` gains a conditional `thin_content: str | None`, populated ONLY on
  a `thin_unverified` outcome, omitted from the wire otherwise (existing
  omit-empty serializer). `query` normally withholds content; this is the
  deliberate exception the index-rule demands.
- Wire-only. A thin/block page never enters cache (never-cache-block-pages).
- `fetch_raw` already returns `content_md`, so a thin `fetch_raw` already carries
  the body — the new field is scoped to `AskResponse` (`query`), the envelope
  that drops content.

## Decision 3 — do not distill a sub-floor body (principle, mostly already true)

No LLM answer is generated for a `thin_unverified` page. Extraction already runs
only on success (`_phase_extract_answer`), so a failed thin page skips it today —
but this is now an explicit principle (ADR-0017: effort ∝ existence prior). The
raw body is handed over for the caller to derive from; a2web does not spend tokens
distilling a <500-char low-prior page. A future change must not add such a call.

## Decision 4 — new internal enum member, not a reuse

`TerminalOutcome.thin_unverified` is distinct from `gone_unverified`: 200-thin →
"read the attached body / accept empty result / reformulate the query"; 404-lone →
"the URL is probably dead, find a replacement URL." Different evidence, residual,
and caller action; different hint text regardless. `TerminalOutcome` is internal
(not wire), so the closed-set cost is one line.

## Endgame (explicitly deferred, not built here)

An empty search result is not a failure — "0 products matched" IS the answer.
The destination is that a corroborated-thin page with readable content returns an
`ok`-shaped answer, not a dressed-up failure. Not v1: it needs a deterministic
empty-vs-wall discriminator a2web does not have. `thin_unverified` + attached body
is the stepping stone; the caller-side loop must prove the attached content
resolves it in practice (watch eval runs) before promoting to `ok`. Logged to
BACKLOG.

## Coherence-table impact

`tests/architecture/test_terminal_hint_coherence.py` gains a `thin_unverified`
row: `frozenset({"content_thin"})`. The mutual-exclusion + only-wall-prescribes-
browser invariants must still hold (`content_thin` is neither `try_user_browser`
nor `content_not_found`).
