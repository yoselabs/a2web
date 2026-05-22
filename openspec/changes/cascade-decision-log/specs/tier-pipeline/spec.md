## MODIFIED Requirements

### Requirement: Orchestrator dispatches browser tier on gate suggested_tier

Browser-tier dispatch SHALL be decided by the planner `decide_next` over the observation log, not by the orchestrator inspecting a gate result inline. When the log carries a gate observation whose evidence maps to browser escalation, `decide_next` SHALL return an `EscalateBrowser` action; the orchestrator executes it by dispatching the browser tier from `REGISTRY` regardless of its absence from `TIER_ORDER`. Because `decide_next` reads the whole log rather than one won tier's gate result, `EscalateBrowser` MAY fire even when no tier produced gate-passing content — a total-failure case the prior gate-gated design could not reach. Browser dispatches SHALL remain capped at 1 per fetch.

A `tls_impersonate` signal observed on the `raw` tier SHALL be a no-op (raw already uses curl_cffi); on any other tier the cascade advances to the next `TIER_ORDER` slot.

#### Scenario: Anubis at jina tier triggers browser escalation

- **WHEN** raw fails, jina returns 200-OK, and the gate observation records an Anubis browser signal
- **THEN** `decide_next` returns `EscalateBrowser`, the orchestrator dispatches the browser tier, and the browser dispatch count is 1

#### Scenario: Browser escalation fires on a total failure

- **WHEN** every live tier fails and no tier produced gate-passing content, but a tier or gate observation records a soft-block / JS-required signal
- **THEN** `decide_next` returns `EscalateBrowser` and the orchestrator dispatches the browser tier

#### Scenario: Browser dispatch capped at 1 per fetch

- **WHEN** the browser tier itself returns a result whose gate observation still carries a browser signal
- **THEN** `decide_next` does NOT return `EscalateBrowser` a second time; the cascade ends failed with the resolved verdict

#### Scenario: tls_impersonate after raw is a no-op

- **WHEN** the raw tier produces a Cloudflare interstitial whose gate observation carries a `tls_impersonate` signal
- **THEN** the cascade does not retry raw; it advances to the next `TIER_ORDER` slot (jina)

### Requirement: Orchestrator executes after-tier RewriteUrl and RetryViaArchive

After each tier appends its observation, the orchestrator SHALL call the planner `decide_next(observation_log, caps)` and execute the returned `Action`. The orchestrator SHALL contain no escalation, rewrite, or stop policy of its own. The actions and their per-fetch caps:

- `RewriteUrl(new_url)` — restart the tier loop with `new_url`; capped at 1 rewrite per fetch.
- `RetryViaArchive(url)` — dispatch the archive tier; capped at 1 archive dispatch per fetch (shared with the after-gate archive path).
- `EscalateBrowser` — dispatch the browser tier; capped at 1 per fetch.
- `StopLiveTiers` — stop dispatching further live (`TIER_ORDER`) tiers; archive escalation MAY still run.
- continue / no-op — advance to the next `TIER_ORDER` slot.

#### Scenario: arxiv pdf rewrites to abs page

- **WHEN** the URL is `https://arxiv.org/pdf/1234.5678` and any tier returns
- **THEN** `decide_next` returns `RewriteUrl("https://arxiv.org/abs/1234.5678")`, the tier loop restarts with the new URL, and the response's `url` field reflects the rewrite

#### Scenario: Rewrite cap prevents loops

- **WHEN** a chain of rewrites would otherwise fire twice in one fetch
- **THEN** the second `RewriteUrl` is not executed; the cascade continues without restart

#### Scenario: Cloudflare 403 after-tier triggers archive dispatch

- **WHEN** the raw tier returns 403 from a Cloudflare-fronted host
- **THEN** `decide_next` returns `RetryViaArchive`, the archive tier is dispatched, and the archive dispatch count is 1

#### Scenario: StopLiveTiers halts live tiers but archive remains allowed

- **WHEN** `decide_next` returns `StopLiveTiers` for an observation log
- **THEN** the orchestrator dispatches no further `TIER_ORDER` tier, while a subsequent `RetryViaArchive` action is still permitted to run

## REMOVED Requirements

### Requirement: Site handler not_found takes precedence over a downstream failure verdict

**Reason**: Superseded by `resolve_verdict` in the new `cascade-decision-log` capability. Verdict precedence is now a uniform projection rule over the observation log, applied to every authoritative signal, rather than a one-off orchestrator reconciliation phase for the single `not_found` case.

**Migration**: The precedence — a site handler's authoritative `not_found` outranks a downstream non-authoritative failure verdict when the fetch fails, and never overrides a genuine recovery — is enforced by `resolve_verdict`'s `(authoritative, verdict)` ordering (see the `cascade-decision-log` capability). `FetchContext.handler_not_found` and `_phase_reconcile_verdict` are removed; their behavior is fully absorbed.
