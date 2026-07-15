# ADR-0017 — Effort ∝ existence prior; confidence ∝ corroboration; severity encodes confidence

**Status:** **Accepted** (decided 2026-07-16)
**Date:** 2026-07-16
**Supersedes:** —
**Superseded by:** —
**Related:** ADR-0009 (never silently miss — this refines *how* a miss is reported), openspec change `fetch-failure-semantics` (full record).

## Context

A live fetch of a dead storefront **search URL** (a genuine HTTP 404) returned `verdict=length_floor` with a **CRITICAL** `try_user_browser` hint — "behind an anti-bot wall, you do NOT have this content". The URL was simply gone. Three tiers saw the 404 (`raw`, our own `browser`, and `jina` — which wraps an upstream 404 as its own HTTP 200), yet the caller was told it was walled and *commanded* to open a browser on a page that does not exist.

The a2web caller is an AI agent, and a CRITICAL operator hint is an **imperative injected into that agent's context**. A miscalibrated failure signal is not noise — it causes a wrong downstream action (burning a browser session on a nonexistent URL). Two structural causes: a tier laundered an error page into `ok` (poisoning the decision log), and the terminal classifier read the *resolved-verdict projection* instead of the *observations* (so corroborating 404 evidence was unreachable).

## Decision

Three tenets, enforced structurally (a pure `classify_terminal` over the decision log, a tier-truthfulness contract, and a tested coherence table):

1. **Escalation effort is proportional to the prior that content EXISTS.** A `200`-but-thin page probably exists behind JS → render hard (browser escalation). A `404` probably does not exist → report it and spend at most ONE cheap soft-404 check, never the full ladder. Spend where recovery is likely, not uniformly.

2. **Terminal confidence is proportional to corroboration.** A "gone" claim is `gone_confirmed` only when an authoritative handler models it, OR ≥2 independent tiers observed the same HTTP not-found. A single uncorroborated 404 is `gone_unverified` — most likely dead, but the soft-404 possibility is disclosed, not asserted away.

3. **Hint severity encodes confidence, not verdict identity.** `info` = a verified fact (a corroborated/authoritative dead URL); `warning` = the check could not be completed (residual uncertainty the caller may resolve); `critical` = every recovery path was attempted and a wall was hit. A dead URL is therefore never `critical`. This is what structurally prevents cry-wolf: the caveat-bearing outcome (`gone_unverified`) is rare, so its `warning` keeps signal.

Corollary — a **tier-truthfulness contract**: a tier that retrieves an error page surfaces the real upstream status (never `ok` merely because bytes arrived), so the decision log — the single source of truth — is never poisoned. Reader-wrapper decoding (jina's `Target URL returned error <status>` stub) is tier work, not gate work.

## Placement — CLAUDE.md + this ADR, NOT CONSTITUTION.md

Per the ADR-0009 / ADR-0012 / ADR-0014 / ADR-0016 precedent: a single project's retrieval-semantics invariant belongs in a2web's `CLAUDE.md` "Never" section with rationale here, not in `CONSTITUTION.md` (verbatim a2kit-synced substrate governance).

## Consequences

- The terminal story is one pure function (`actions/terminal.classify_terminal`), the backward-looking sibling of the `playbook` — the two inverse whitelist predicates (`_is_genuine_gone` / `_prescribe_browser_on_wall`) are retired.
- `OperatorHint.severity` gains `warning` (the single wire change).
- A `tests/architecture/` coherence table forbids the incoherent combination that shipped (`wall` prescription + `gone` signal on one outcome).
- Not solved here (documented follow-up): a **200-soft-404** (HTTP 200 + a "no results" body) carries zero status evidence and still gates to `length_floor`; its narrative must hedge, and it is captured in the corpus.
