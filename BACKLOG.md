# Backlog

Deferred items from the v0.1 build, grouped by target milestone. Each entry
records its source (PR id or engineering doc section), a one-line
description, why it was deferred, and a rough scope tier (S / M / L).

> **Lifecycle.** Items are removed in the change that ships them, and added
> by any future OpenSpec change whose proposal carries an "Out of Scope"
> deferral. Keep this file current — every change that defers adds, every
> change that ships removes.
>
> **Single source of truth.** This file consolidates every known
> deferral. Upstream context: `~/Documents/Knowledge/Projects/120-a2web/v0.1-engineering.md`
> §10 (original v0.2/v0.3 deferrals); §9 (build order) is fully shipped
> and lives in `openspec/changes/archive/`. New deferrals land here, not
> in design docs.

---

## PR7e — Proxy polish

- **Browser-tier proxy plumbing.** Source: PR7d / PR7c. Camoufox is
  context-level (proxy lives on the persistent context, not the page);
  the v0.1 pool resolves and reports but does not configure browser
  contexts. *Why deferred:* per-host context coupling needs rework and
  is a separate scope from the orchestrator's proxy contract. Scope: M.
- **Archive-tier proxy plumbing.** Source: PR7d. Wayback / archive.ph
  hedge requests bypass the proxy pool today. *Why deferred:* the
  hedged-request task group needs proxy-aware retry semantics. Scope: M.
- **Persistent `~/.a2web/proxy-health.json`.** Source: PR7d. Health is
  in-memory only at v0.1. *Why deferred:* survives a single process;
  multi-process / restart-friendly health is a v0.2 concern. Scope: S.
- **Background health-check loop.** Source: PR7d. Quarantine is
  reactive (3 failures → 600s). *Why deferred:* proactive probes are
  observability work; in-memory reactive policy is sufficient for v0.1.
  Scope: M.
- **`a2web profile` CLI commands.** Source: PR7d. *Why deferred:* the
  multi-profile system itself is post-v0.1; CLI follows the model.
  Scope: M.
- **Global circuit breaker alarming.** Source: PR7d. Hooks exist;
  alerting does not. *Why deferred:* alerting is observability work,
  out of scope for the cascade. Scope: S.

## PR7c follow-ups

- **Anubis PoW solver / Turnstile auto-solve / cookie-consent dismissal.**
  Source: PR7c. *Why deferred:* Camoufox + realistic timing handles
  most observed cases; explicit solvers wait for v0.2 evidence. Scope: L.
- **Profile-keyed browser contexts.** Source: PR7c. *Why deferred:* the
  profile system itself is post-v0.1. Scope: M.

## PR8b — Site handlers

- **`youtube` handler.** Source: PR8. *Why deferred:* needs the browser
  tier or a `yt-dlp` opt-in dependency; both are non-trivial. Scope: M.
- **`substack` handler.** Source: PR8. *Why deferred:* trafilatura
  already handles articles; per-domain auto-detection complexity is not
  worth it without signal. Scope: S.
- **`twitter` / X handler.** Source: PR8. *Why deferred:* auth-gated;
  no clean v0.1 path. Scope: L.
- **Per-handler proxy plumbing.** Source: PR8. *Why deferred:* mostly
  mechanical — bundle with PR7e proxy work. Scope: S.

## PR10b — Replay from cache

- **`a2web fetch --replay <ts>`.** Source: PR10. *Why deferred:* needs
  body storage in the NDJSON log; the v0.1 log records metadata only.
  Scope: M.
- **`a2web logs stats` / `--format csv` export.** Source: PR10. *Why
  deferred:* defer until usage signals which aggregations matter; do
  not pre-build dashboards no one reads. Scope: S.

## v0.2 candidates

- **Reader-LM v2 fallback.** Source: engineering.md §10. *Why deferred:*
  trip only if a benchmark shows trafilatura + readability misses ≥10%
  of content; otherwise the cost isn't justified. Scope: L.
- **Multimodal fetch (screenshot + DOM as response).** Source:
  engineering.md §10. *Why deferred:* requires the browser tier to
  emit screenshots and a response-shape change; v0.2 contract decision.
  Scope: L.
## v0.3+

- **Browser-as-a-service remote CDP.** Source: engineering.md §10. *Why
  deferred:* removes the local Camoufox dep at the cost of a network
  hop and a service to operate. Scope: L.
- **VLM image captioning.** Source: engineering.md §10. *Why deferred:*
  vision pipeline. Scope: L.
- **Distributed cache (remote backend).** Source: engineering.md §10.
  *Why deferred:* sqlite is sufficient for single-operator use. Scope: L.
- **Webhook callbacks for slow fetches.** Source: engineering.md §10
  (vision). *Why deferred:* event-sink pattern, not yet needed. Scope: M.
- **LLM-emitted hints.** Source: engineering.md §10 (vision). *Why
  deferred:* needs an evaluation harness first. Scope: L.

## v1.0 / vision

- **Search aggregation as primary surface.** Source: engineering.md §10
  (v1.0). *Why deferred:* a separate product surface, not a tier in
  the cascade. Scope: L.
