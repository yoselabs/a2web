## Context

Jina (PR7a) recovers tier-level failures only. The bigger v0.1 gap is post-gate failures: paywall/block-page on a 200-OK, where the live HTML is junk but Wayback or archive.ph holds a clean copy. The playbook also captures URL-shape transformations the orchestrator can do without LLM judgment.

## Goals / Non-Goals

**Goals:**
- Archive tier hedges Wayback CDX + archive.ph and returns whichever lands first
- Playbook is deterministic, pure, and unit-testable without I/O
- No new deps; archive uses curl_cffi (already present) for the Cloudflare-fronted archive.ph

**Non-Goals:**
- Smart re-extraction across archive vs. live (one extraction pass; archive HTML has Wayback chrome stripped via a regex pass before trafilatura)
- Multi-rewrite chains (cap at 1 per fetch — anti-loop)
- Agent-actionable hints feeding back to the playbook (kept pure)

## Decisions

**Hedging via `anyio.create_task_group()` with explicit cancellation.**
Both upstreams are launched as soon-tasks; the first to land a `verdict == ok` result writes to a `MemoryObjectSendStream` that the parent reads. The other task is cancelled by the task group exit. Alternative: `asyncio.wait(FIRST_COMPLETED)` — rejected; mixes asyncio + anyio and complicates cancellation propagation.

**Wayback strip via regex, not full HTML rewriting.**
Wayback wraps pages in a fixed `<div id="wm-ipp-base">…</div>` chrome plus a script tag at the end. A two-line regex `re.sub(r'<div id="wm-ipp-base".*?</div>', '', body, flags=re.S)` removes it before trafilatura sees the body. Pure cosmetic; survivors of the chrome are extracted normally.

**Playbook as a list-of-rules, not a class hierarchy.**
`_RULES: list[Callable[[Context], Action | None]]` — first non-None wins. Each rule is ~5 lines and unit-tested in isolation. Alternative: a Strategy class per rule — rejected; over-abstracted for v0.1's 4 entries.

**Anti-loop cap: 1 rewrite + 1 archive retry per fetch.**
The orchestrator tracks a small `playbook_state` dict on the stack (not in AppState; per-fetch). After one rewrite OR one archive dispatch, further `RewriteUrl`/`RetryViaArchive` returns from the playbook are ignored. Alternative: depth-limit recursion — rejected; explicit counter is simpler and matches "no retry storms" rule.

**Archive tier is in REGISTRY but NOT in TIER_ORDER.**
The orchestrator dispatches it out-of-band when the playbook says so. Default fetches never invoke it. Alternative: append to TIER_ORDER and skip via a flag — rejected; reading `TIER_ORDER` should always reflect *what runs*.

## Risks / Trade-offs

- **Archive freshness lag** → Wayback can be 24h+ stale; we accept this and leave a `tier_extras["snapshot_age_days"]` hint for callers
- **archive.ph rate limiting** → curl_cffi + chrome120 fingerprint should pass; if not, the hedge still wins via Wayback
- **Playbook miscategorization** (rewriting a URL that didn't need it) → conservative table; only triggers on closed-enum verdicts and explicit URL patterns
- **Hedge cancellation noise** → cancelled task may emit a stray log line; suppress via try/except on `anyio.get_cancelled_exc_class()`

## Migration Plan

1. Land `actions/playbook.py` with empty rule list; orchestrator wired but no-ops.
2. Add archive tier; smoke against a known paywalled URL through `RetryViaArchive`.
3. Populate playbook rules one-at-a-time with tests.

Rollback: revert commit. No persisted state; cache is unaffected (archive results don't write to the live cache namespace — `tier_extras["from_archive"]=True` skips cache write).

## Open Questions

- Should archive results write to a *separate* cache namespace? (Probably yes in PR7c when proxy pool lands; for v0.1 just don't cache.)
- Do we want an `A2WEB_ARCHIVE_DISABLED` env flag for users behind networks that block archive.org? (Defer until anyone asks.)
