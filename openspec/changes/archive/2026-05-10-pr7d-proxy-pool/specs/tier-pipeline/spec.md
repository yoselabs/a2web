## ADDED Requirements

### Requirement: Orchestrator resolves a proxy route per tier invocation

Before each tier call, the orchestrator SHALL call `pool.acquire(host, tier_name)` and pass the resulting `proxy_url` (or `None`) into the tier. The orchestrator SHALL populate `Diagnostic.proxy` with the resolved proxy id (or `"direct"`) for that tier's diagnostic row.

When `acquire` returns `None` (all proxies dead AND `proxy_required=True`), the orchestrator SHALL skip that tier with a `Verdict.proxy_unavailable` diagnostic and advance to the next `TIER_ORDER` slot. When the tier itself returns `Verdict.proxy_unavailable`, the orchestrator SHALL `report(handle, success=False)` and apply the same skip-or-advance logic.

#### Scenario: Diagnostic carries proxy id

- **WHEN** raw fetch goes through `residential_eu`
- **THEN** the raw diagnostic row has `proxy == "residential_eu"`

#### Scenario: All proxies dead with proxy_required skips tier

- **WHEN** all proxies for raw on host X are quarantined and the rule has `proxy_required=True`
- **THEN** raw is skipped (no fetch attempt), `Verdict.proxy_unavailable` diagnostic recorded, and the orchestrator advances to jina

### Requirement: Orchestrator executes after-tier RewriteUrl and RetryViaArchive

After each tier produces a result, the orchestrator SHALL consult `next_action_after_tier(tier_result, current_url, settings)`:

- `RewriteUrl(new_url)` — restart the tier loop with `new_url`. Capped at 1 rewrite per fetch (per-fetch counter `url_rewrites`). Subsequent rewrites SHALL be ignored.
- `RetryViaArchive(url)` — dispatch the archive tier as in the after-gate path. Shares the existing `archive_dispatches` cap (1 per fetch); after-tier and after-gate are mutually exclusive paths.
- `Skip` / `None` — no-op.

#### Scenario: arxiv pdf rewrites to abs page

- **WHEN** the URL is `https://arxiv.org/pdf/1234.5678` and any tier returns
- **THEN** the playbook returns `RewriteUrl("https://arxiv.org/abs/1234.5678")`, `url_rewrites` increments to 1, the tier loop restarts with the new URL, and the response's `url` field reflects the rewritten URL

#### Scenario: Rewrite cap prevents loops

- **WHEN** a chain of rewrites would otherwise fire twice in one fetch
- **THEN** the second `RewriteUrl` is ignored; the orchestrator continues without restart

#### Scenario: Cloudflare 403 after-tier triggers archive dispatch

- **WHEN** raw returns 403 from a Cloudflare-fronted host (`server: cloudflare`)
- **THEN** `next_action_after_tier` returns `RetryViaArchive`, the archive tier is dispatched out-of-band, and `archive_dispatches` increments to 1

#### Scenario: After-tier and after-gate share archive cap

- **WHEN** after-tier dispatches archive (cap consumed) and a later gate verdict would also dispatch archive
- **THEN** the second dispatch is suppressed; the original gate verdict stands
