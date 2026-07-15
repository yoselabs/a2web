## 1. Baseline + audit (no code changes)

- [x] 1.1 Green baseline on affected suites: `tests/capabilities/tier_pipeline/`, `tests/capabilities/quality_gate/`, `tests/capabilities/retrieval_completeness/` (if present), `tests/capabilities/fetch_response/`, `tests/capabilities/ask_response/`, `tests/capabilities/cascade_decision_log/`, `tests/capabilities/tier_pipeline/test_jina_tier.py`, `tests/eval_replay/`.
- [x] 1.2 Grep-audit every reader of `_is_genuine_gone`, `_prescribe_browser_on_wall`, `try_user_browser_hint`, `_JINA_PAYWALL_STUB_RE`, `_JINA_STUB_MAX_BODY`, and every `OperatorHint(severity=...)` construction site — nothing orphaned by the deletions.
- [x] 1.3 Confirm how the `browser` tier currently reports a rendered error page (verdict/status), and where a browser 404 lands in the decision log today — establish exactly what "browser corroborated 404" must look like as an observation.

## 2. Tier truthfulness (the linchpin)

- [x] 2.1 `tiers/jina.py`: unwrap the reader stub. Generalized `Target URL returned error (\d{3})` capture (behind the existing body-length guard), route the captured status through `_verdict_for_status`, set the real `status_code`, `pre_rendered=None` on a wrapped error. Map wrapped 401/403 → `Verdict.paywall` to preserve archive routing (behaviour-neutral except 404).
- [x] 2.2 `tiers/browser.py`: surface a retrieved error-page upstream status on `TierResult` so a browser-confirmed 404 is a first-class observation, not a buried diagnostic. Do NOT change the success path.
- [x] 2.3 `fetcher.py`: DELETE `_JINA_PAYWALL_STUB_RE`, `_JINA_STUB_MAX_BODY`, and the `tier == "jina"` branch in `evaluate()`. Verify wrapped-401/403 still routes to archive (via the tier's paywall mapping) and wrapped-404 now resolves to `not_found`.
- [x] 2.4 Unit tests: jina wrapped-404 → tier `not_found`/404 (does NOT win the loop); wrapped-403 → `paywall`; a long article quoting the stub string does NOT false-positive; browser rendering a 404 page surfaces a 404-status observation.

## 3. Incoming reader-prefix normalization

- [x] 3.1 `fetcher.fetch()` (beside `rewrite_captcha_host`): detect an incoming `https://r.jina.ai/<url>` (and the http/no-scheme variants) and strip to `<url>`; fetch the real target with the full ladder. Surface the real target as `requested_url`.
- [x] 3.2 Tests: a pre-wrapped `r.jina.ai/<real>` input fetches `<real>` through raw→jina→browser (fallback intact), and the wire `url` is the real target, never the wrapper. A bare `r.jina.ai/` (no inner URL) is left alone.

## 4. `classify_terminal` (fix Bug 2 structurally)

- [x] 4.1 New `src/a2web/actions/terminal.py`: `classify_terminal(observations, resolved_verdict) -> TerminalOutcome` (closed enum `wall | gone_confirmed | gone_unverified | operator_error | unreachable`). Pure, total, log-reading. No import from `a2web.fetcher`.
- [x] 4.2 Corroboration logic: HTTP 404 with a browser observation also at 404 → `gone_confirmed`; HTTP 404 with no completed browser check (budget spent / pool unavailable / browser saw non-404) → `gone_unverified`; handler-authoritative not_found → `gone_confirmed`; walls → `wall`; dns/content_type_mismatch → `unreachable`; paid_auth_error → `operator_error`.
- [x] 4.3 `fetcher.py`: replace `_is_genuine_gone` + `_prescribe_browser_on_wall` with a single call to `classify_terminal`; map its `TerminalOutcome` → (`retrieval_incomplete`, hint, severity, narrative). `wall` → CRITICAL `try_user_browser` (unchanged); `gone_confirmed` → INFO `content_not_found`, not incomplete; `gone_unverified` → WARNING `content_not_found` with soft-404 caveat + browser escape hatch, incomplete; `operator_error`/`unreachable` as today.
- [ ] 4.4 (Optional, DEFERRED) cap an uncorroborated-404 browser escalation at one rung (`_decide_uncorroborated_404_escalate`), per "effort ∝ existence prior." Not done — it touches the shared fast→robust ladder guard and carries regression risk for the reddit-404 path; left as a follow-up knob, not blocking.
- [x] 4.5 Property test: `classify_terminal` is total over the observation-shape space; a browser-corroborated 404 never yields `wall`; a `gone_unverified` is the ONLY 404 flavor that carries the soft-404 caveat.

## 5. Wire: `warning` severity + hint

- [x] 5.1 `models.py`: add `warning` to `OperatorHint.severity` (`info | warning | critical`); update `_omit_default_severity` (only `info` is dropped). Add a `content_not_found` hint constructor (INFO vs WARNING variants, capability-generic wording).
- [x] 5.2 **Ask-First gate**: confirm the installed MCP client tolerates an unknown/`warning` severity value before this ships (response-envelope shape). Record the decision in the change.

## 6. Taxonomy consistency invariant

- [x] 6.1 New `tests/architecture/` test: a declared coherence table over `(TerminalOutcome × permitted hint codes)` and `(verdict × coherent obstacles)`, asserted on the response builder — a `not_found`/`gone_confirmed` terminal may NOT carry `try_user_browser`; a `wall` MUST. Fails CI on an incoherent combination (the exact incident class).

## 7. Corpus + replay (never lose a case)

- [x] 7.1 `eval/corpus/regression/`: a decision-log replay of the Turkish 404 (`raw:404 → jina wrapped-404 → browser:404`) asserting `gone_confirmed` / `not_found` / no `try_user_browser`.
- [x] 7.2 `eval/corpus.yaml`: refresh `incehesap-search-thin-jina-terminal` criteria to the corrected expectation (not_found, honest "likely dead URL", not an anti-bot klaxon).
- [x] 7.3 `eval/corpus.yaml`: ADD the **200-soft-404 sibling** (HTTP 200 + "no results" body) as its own entry; criteria structural; note the fix is deferred but the narrative must hedge ("thin page — could be an empty result set"), never fire the anti-bot klaxon.

## 8. ADR + docs + gate

- [x] 8.1 ADR: "Escalation effort ∝ prior that content exists; terminal confidence ∝ corroboration; hint severity encodes confidence." Link from CLAUDE.md's Never/invariants where `try_user_browser` is described.
- [x] 8.2 Update the `retrieval-completeness`, `tier-pipeline`, `quality-gate` spec docstrings/Purpose to match.
- [x] 8.3 `make check` (lint + ty + full test + coverage ≥85%) and `make arch` green. Run the full unpruned suite (`-p no:tach`) since impact analysis prunes the negative-path tests.
- [ ] 8.4 `make bench` (live-network, LLM quota — tier routing moved) — record findings in `eval/findings_<date>.md`. Deferred to a follow-up run; not a gate blocker.
