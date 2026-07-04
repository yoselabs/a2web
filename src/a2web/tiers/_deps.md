# Dependency decisions — `src/a2web/tiers/`

Article VIII (Constitution) dependency memory for the tier layer. Every
adopted and rejected external fetch backend is recorded here with a link to
its ADR, so none is re-litigated as a "fresh idea." Read this before proposing
or re-evaluating any fetch backend.

## Adopted

### Dep: Zyte API — adopted for paid last-resort fetch
- **subpackage:** `src/a2web/tiers/` (`zyte.py` + `_manifests/tiers/zyte.py`)
- **decision:** adopt (env-gated; runtime-optional, no new install dep — plain `httpx` POST)
- **problem space:** anti-bot / Datadome walls the free ladder (raw → jina → browser → archive) cannot pass.
- **considered_alternatives:** Firecrawl (also adopted, sibling), Reddit OAuth (deferred), Redlib (rejected), proxy-through-Shen (rejected) — see ADR-0010.
- **citable_reasons:**
  - Pay-as-you-go (`~$0.13/1K`), the Scrapy company — most reputable of the paid options.
  - Server-side rendering + challenge solving (`browserHtml`) is exactly the capability the free ladder lacks.
- **wiring:** keyed by `A2WEB_ZYTE_KEY` (env-only secret; dropped from YAML). Manifest `priority=-1` (out-of-band, never in `TIER_ORDER`). Un-keyed → `Unavailable`, tier never registers. Bad key (401/402/403) → authoritative `Verdict.paid_auth_error`, STOPs escalation (never a silent downgrade).
- **re_evaluation_triggers:**
  - Trial-key validation (task 4.9) shows Zyte does NOT actually pass Reddit's Datadome → drop or replace.
  - A keyless path (RSS + logged-in `.json`) proves sufficient → the paid tier becomes dead weight.
- **ADR:** [ADR-0010](../../../docs/adr/0010-reddit-reachability-access-paths.md) · **last_reviewed:** 2026-07-03

### Dep: Firecrawl API — adopted for paid last-resort fetch
- **subpackage:** `src/a2web/tiers/` (`firecrawl.py` + `_manifests/tiers/firecrawl.py`)
- **decision:** adopt (env-gated; runtime-optional, plain `httpx` POST)
- **problem space:** same wall as Zyte; a second independent paid backend (auto-reorder / redundancy).
- **considered_alternatives:** Zyte (sibling, tried first), see ADR-0010.
- **citable_reasons:**
  - AI-native, returns clean markdown directly (`formats: ["markdown"]`) — no local extraction needed.
  - Already partially wired in earlier exploration; low marginal cost to finish.
- **wiring:** keyed by `A2WEB_FIRECRAWL_KEY`. Same manifest gating + `paid_auth_error` fail-loud contract as Zyte. Tried after Zyte in `_PAID_TIER_ORDER`, and only on a non-auth Zyte failure (an auth error STOPs before it).
- **re_evaluation_triggers:** same as Zyte.
- **ADR:** [ADR-0010](../../../docs/adr/0010-reddit-reachability-access-paths.md) · **last_reviewed:** 2026-07-03

## Rejected / deferred

Recorded in full in [ADR-0010](../../../docs/adr/0010-reddit-reachability-access-paths.md) with reasons + re-evaluation triggers: **Redlib** (rejected — OAuth spoofing), **PullPush.io** (deferred — ~14mo stale ingest), **Reddit OAuth** (deferred — Nov-2025 approval gate), **proxy-through-Shen** (rejected — datacenter ASN + JS challenge), **Chrome-inside-a2web / rdt-cli / OpenCLI / Agent-Reach login-CLIs** (rejected for remote — local-desktop cookie architectures). Read that ADR before re-proposing any of them.
