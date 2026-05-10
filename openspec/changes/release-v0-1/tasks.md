# Implementation Tasks

## 1. Prerequisite

- [ ] 1.1 Confirm `remove-logs-router` change has been archived and its commit landed on `main`. If not, stop and run that change first.

## 2. Version bump

- [ ] 2.1 Edit `pyproject.toml`: change `version = "0.1.0.dev0"` to `version = "0.1.0"`
- [ ] 2.2 Confirm classifiers still include `Development Status :: 3 - Alpha` (intentional — Alpha is honest for v0.1)
- [ ] 2.3 No other `[project]` field changes

## 3. CHANGELOG.md

- [ ] 3.1 Create `CHANGELOG.md` at repo root using Keep-a-Changelog format
- [ ] 3.2 Top section: `## [0.1.0] - 2026-05-10`
- [ ] 3.3 Under `### Added`: cascade summary with PR references — site_handler / raw / jina tiers, archive escalation (PR7b), Camoufox browser tier (PR7c), proxy pool with after-tier action execution (PR7d), arxiv/wikipedia/github handlers (PR8), gate signal table, NDJSON request log
- [ ] 3.4 Under `### Removed`: `LogsRouter` MCP/CLI surface from prerelease (PR10 + remove-logs-router) — note that the on-disk NDJSON log is unchanged
- [ ] 3.5 Header note: "First tagged release; entries summarize the full PR1–PR10 build."

## 4. BACKLOG.md

- [ ] 4.1 Create `BACKLOG.md` at repo root with grouped sections
- [ ] 4.2 **PR7e — Proxy polish** group: browser-tier proxy plumbing (Camoufox context-level), archive-tier proxy plumbing, persistent `~/.a2web/proxy-health.json`, background health-check loop, `a2web profile` CLI commands, global circuit breaker alarming
- [ ] 4.3 **PR7c follow-ups**: Anubis PoW solver, Turnstile auto-solve, cookie-consent dismissal filter, profile-keyed browser contexts
- [ ] 4.4 **PR8b — Site handlers** group: youtube (browser tier or yt-dlp opt-in dep), substack (per-domain detection), twitter/X (auth-gated)
- [ ] 4.5 **PR8 follow-ups**: per-handler proxy plumbing
- [ ] 4.6 **PR10b — Replay-from-cache** group: rerun pipeline against stored body without re-fetching, `a2web fetch --replay <ts>`, `a2web logs stats`, `a2web logs export --format csv`
- [ ] 4.7 **v0.2 candidates** group (engineering.md §10): Reader-LM v2 fallback (only if benchmark shows trafilatura+readability misses ≥10%), multimodal fetch (screenshot+DOM as response), browser-as-a-service remote CDP
- [ ] 4.8 **v0.3+** group: VLM image captioning, distributed cache (remote), webhook callbacks for slow fetches, LLM-emitted hints, search aggregation as primary
- [ ] 4.9 Each entry: source reference, one-line description, why deferred, scope tier (S/M/L)
- [ ] 4.10 Header note: "Deferred items from v0.1 build. Items are removed when shipped, added when new deferrals appear in OpenSpec change proposals."

## 5. README.md (light touch)

- [ ] 5.1 Read current `README.md`. If it carries `dev0`, "in development", "WIP", or "TODO" caveats, replace with v0.1 install + quickstart
- [ ] 5.2 Add a single line near the bottom: "See [BACKLOG.md](./BACKLOG.md) for deferred work."
- [ ] 5.3 If README is already version-agnostic, skip — do not gold-plate

## 6. CLAUDE.md (cross-reference)

- [ ] 6.1 Add a one-line bullet under the "Conventions" or top section: "BACKLOG.md tracks deferred work; keep it current — every change that defers an item adds it, every change that ships one removes it."

## 7. Gate

- [ ] 7.1 `make lint` clean
- [ ] 7.2 `make ty` clean
- [ ] 7.3 `make test` green, coverage ≥85%
- [ ] 7.4 Commit with message `Release v0.1.0`
- [ ] 7.5 Annotate tag: `git tag -a v0.1.0 -m "a2web v0.1.0 — cascade feature-complete"`
- [ ] 7.6 **Do NOT push the tag** — operator decides whether/when
- [ ] 7.7 Archive change via `openspec archive release-v0-1`
