## Why

PR7a wired Jina as a tier-failure fallback, but the cascade still has nothing to offer when the *gate* (post-fetch) fires `paywall`, `block_page_detected`, or `length_floor` on a 200-OK response. Reading the spike-2026-05-07 ground-truth, ~half the "failed v0.1" URLs are paywalls or anti-bot pages — the **archive tier** (Wayback CDX + archive.ph hedged) is the canonical recovery path. PR7b adds it.

The other half of the playbook is the **autonomous-action table** from `v0.1-design.md` §autonomous-actions: when raw returns `403` from a Cloudflare-fronted host, automatically retry through archive; when extract finds an arxiv abstract page, swap to the html alternate; etc. These are deterministic transformations, not agent decisions — they belong in a pure `playbook.py` module the orchestrator consults between tiers.

## What Changes

- `tiers/archive.py`: `ArchiveTier` implementing the `Tier` protocol. Hedges two upstreams in parallel via `anyio.create_task_group()`:
  - **Wayback CDX**: `GET https://web.archive.org/cdx/search/cdx?url=<url>&output=json&limit=1&fl=timestamp,original`. If a snapshot exists, fetch `https://web.archive.org/web/<timestamp>/<url>`.
  - **archive.ph**: `GET https://archive.ph/newest/<url>` with curl_cffi (Cloudflare-fronted; needs TLS impersonation).
  Whichever returns first with `verdict == ok` wins; the other is cancelled. Result populates `tier_extras["pre_rendered"]` on the markdown body extracted via trafilatura inside the tier (since archive HTML has very different selectors than the live page).
- `actions/playbook.py`: pure functions `next_action_after_tier(tier_result, url, settings) -> Action | None` and `next_action_after_gate(verdict, url, settings) -> Action | None`. `Action` is a closed-enum union: `RetryViaArchive(url)`, `RewriteUrl(new_url)`, `Skip`. No agent decisions; first-match dispatch.
- Orchestrator consults the playbook **after** each tier's gate verdict. When the playbook returns `RetryViaArchive`, the orchestrator inserts the archive tier at the next slot regardless of `TIER_ORDER` position. When it returns `RewriteUrl`, the loop restarts with the new URL (capped at 1 rewrite per fetch — anti-loop).
- `TIER_ORDER` *unchanged* — archive is opt-in via the playbook. Adding it to the default cascade would burn ~3s per blocked fetch even when raw is fine.
- v0.1 playbook entries (kept conservative):
  - paywall verdict → archive
  - block_page_detected verdict → archive
  - 403/429 from cloudflare-fronted host → archive
  - `arxiv.org/pdf/<id>` URL → rewrite to `arxiv.org/abs/<id>` (arxiv handler in PR8 will re-rewrite to abs page)
  - All other cases → None (no-op)

## Capabilities

### New Capabilities
- `archive-tier`: hedged Wayback + archive.ph fallback, opt-in via playbook
- `playbook`: pure deterministic action table that maps tier/gate verdicts to followup actions

### Modified Capabilities
- `tier-pipeline`: orchestrator consults `playbook` after each tier's gate; archive tier dispatched out-of-order on `RetryViaArchive`

## Impact

- `pyproject.toml`: no new deps (curl_cffi + httpx already there)
- `src/a2web/tiers/archive.py`: new file, ~150 LOC
- `src/a2web/actions/__init__.py` + `playbook.py`: new package
- `src/a2web/fetcher.py`: post-tier playbook consult + 1-rewrite cap
- `src/a2web/tiers/__init__.py`: register archive but **not** in `TIER_ORDER`
- Tests: archive happy path (cdx hit, archive.ph hit, both miss), hedge winner cancellation, playbook table, orchestrator rewrite cap
