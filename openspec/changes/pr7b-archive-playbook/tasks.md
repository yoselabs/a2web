# Implementation Tasks

## 1. Playbook (no dependencies)

- [x] 1.1 Create `src/a2web/actions/__init__.py`
- [x] 1.2 Create `src/a2web/actions/playbook.py` with `Action` union dataclasses (`RetryViaArchive`, `RewriteUrl`, `Skip`)
- [x] 1.3 Implement `next_action_after_gate(verdict, url, settings)` with paywall + block-page rules
- [x] 1.4 Implement `next_action_after_tier(tier_result, url, settings)` with cloudflare-403 + arxiv-pdf rules
- [x] 1.5 Tests: each rule individually; precedence; no-op default

## 2. Archive tier

- [x] 2.1 Create `src/a2web/tiers/archive.py` skeleton (`name = "archive"`, async fetch)
- [x] 2.2 Implement Wayback CDX lookup + snapshot fetch via httpx
- [x] 2.3 Implement archive.ph fetch via curl_cffi (chrome120)
- [x] 2.4 Implement hedge via `anyio.create_task_group()` + first-success memory stream
- [x] 2.5 Implement Wayback chrome strip via regex; trafilatura → markdown
- [x] 2.6 Set `tier_extras` keys: `from_archive`, `source`, `snapshot_age_days`
- [x] 2.7 Register in `REGISTRY` (NOT in `TIER_ORDER`)
- [x] 2.8 Tests: wayback hit, archive.ph hit, both miss, hedge cancellation

## 3. Orchestrator integration

- [x] 3.1 Add per-fetch counters `archive_dispatches`, `url_rewrites` to the orchestrator stack
- [x] 3.2 Call `next_action_after_tier` after each tier result; honor `RetryViaArchive` / `RewriteUrl` with caps
- [x] 3.3 Call `next_action_after_gate` after gate runs; honor paywall/block-page → archive
- [x] 3.4 Skip cache write when `tier_result.tier_extras.get("from_archive")` is True
- [x] 3.5 Tests: paywall → archive end-to-end; rewrite cap; archive cap

## 4. Gate

- [x] 4.1 `make lint` clean
- [x] 4.2 `make ty` clean
- [x] 4.3 `make test` green, coverage ≥85%
- [x] 4.4 Live demo: known paywall URL produces archive-tier success
- [x] 4.5 Update `CLAUDE.md` (archive tier, playbook module, anti-loop caps)
- [x] 4.6 Commit `PR7b: archive tier + playbook`
- [x] 4.7 Archive change via `openspec archive pr7b-archive-playbook`
