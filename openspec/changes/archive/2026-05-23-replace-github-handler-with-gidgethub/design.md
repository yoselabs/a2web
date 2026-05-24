## Context

`handlers/github.py` was written before any GitHub-specific library was on the team's radar. It does five things: (1) URL shape detection, (2) endpoint construction, (3) HTTP via curl_cffi, (4) response parsing + pagination + rate-limit handling, (5) markdown rendering. Items 2-4 are stock GitHub API client work — exactly the territory `gidgethub` was built for. Item 1 is one-line `urlparse`. Item 5 is a2web-specific.

The architectural pattern we need is "outsource plumbing, keep formatter". The blocker for using PyGithub or githubkit is that both own their own HTTP transport — adopting them would route GitHub traffic *around* our breakers, proxies, and curl_cffi TLS fingerprint. `gidgethub` is the rare API client that solved this correctly: it's sans-IO. You give it response bytes; it gives you parsed dicts plus the next request to make. The transport is yours.

This same pattern is the one we should apply across handlers wherever a sans-IO client exists. GitHub is the cleanest first case because gidgethub is well-maintained and the API surface is large enough that hand-rolling has measurable rot risk.

## Goals / Non-Goals

**Goals:**
- Shrink `handlers/github.py` by removing hand-rolled pagination, rate-limit decoding, base64 unwrap, and URL construction.
- Route every GitHub API request through our existing curl_cffi tier so breakers / proxies / TLS fingerprint apply uniformly.
- Preserve the existing markdown output byte-for-byte where the formatter input is unchanged. Where gidgethub gives us a richer parsed object than the hand-rolled path, the formatter is allowed to use it — but the rendered markdown SHALL match the existing snapshot tests.
- Preserve the `Verdict.rate_limited` contract on 429 / `X-RateLimit-Remaining: 0`.

**Non-Goals:**
- No move into GraphQL. The REST surface is sufficient for the three URL shapes a2web handles. gidgethub's GraphQL support exists but is out of scope.
- No introduction of typed `gidgethub` models into the handler's public surface. `pre_rendered.content_md: str` stays as the only output.
- No new `packages/` module. The transport adapter is too small and too domain-coupled (knows about a2web's `curl_cffi` session + the handler's User-Agent / token plumbing) to justify a package boundary.
- No change to handler dispatch in `handlers/__init__.py`.

## Decisions

### D1 — gidgethub over PyGithub / githubkit

**Decision**: Adopt `gidgethub`.

**Why**: It is the only major GitHub Python lib that is sans-IO. PyGithub owns urllib3; githubkit owns httpx. Both would bypass our curl_cffi tier, defeating the breakers, proxy routing, and TLS-fingerprint logic that makes a2web work against bot-walled hosts. Sans-IO means "bring your own transport" — perfect fit.

**Alternatives considered**:
- *PyGithub*: rejected (owns transport). Would force a parallel HTTP path that breaks our resilience model.
- *githubkit*: rejected (owns transport). Same problem; nicer typing, but typing was not the bottleneck.
- *Stay hand-rolled*: rejected (the whole point of this change).
- *Use `gidgethub.aiohttp` / `gidgethub.httpx`*: rejected — those *are* gidgethub's bundled transports. We use `gidgethub.sansio.GitHubAPI` directly with our own transport adapter.

### D2 — Transport adapter is inline in `handlers/github.py`, not a `packages/` module

**Decision**: A ~30 LoC `_CurlCffiGitHubTransport` class inside `handlers/github.py` implements `gidgethub.sansio` request execution by calling our curl_cffi session.

**Why**: The adapter knows about a2web-domain things (settings, structlog binding, our specific curl_cffi session). Per the `packages/` independence rule, anything that knows about domain modules cannot live in `packages/`. A new `packages/github_transport/` would have to either accept the curl_cffi session as a kwarg (over-engineering for ~30 LoC) or break the rule (no).

**Alternatives considered**:
- *New `packages/sansio_http_transport/` exposing a generic sans-IO adapter*: defer until we have a second sans-IO consumer. YAGNI.
- *Inline as a closure inside `_handle_*` functions*: rejected — harder to test in isolation.

### D3 — Markdown output is the contract; gidgethub's parsed shapes are an implementation detail

**Decision**: The markdown formatters (`_render_repo_md`, `_render_issue_md`, `_render_pull_md`) keep their existing signatures (they consume dicts). gidgethub gives us dicts directly from its sans-IO `getitem` / `getiter` calls.

**Why**: We don't want to leak gidgethub's parsed-object types into the rest of a2web. The markdown output is what spec scenarios test ("renders title + body + comments in chronological order"); the parsed-dict shape is incidental.

**Alternatives considered**:
- *Pass gidgethub's typed objects through to the formatter*: rejected — couples our formatter to upstream's evolution and to `gidgethub` import in places that don't need it.

### D4 — Rate limit handling via `gidgethub.RateLimitExceeded`, not header peeking

**Decision**: Catch `gidgethub.RateLimitExceeded` at the dispatch sites and emit `verdict == Verdict.rate_limited` + the `A2WEB_GITHUB_TOKEN` operator hint.

**Why**: gidgethub parses `X-RateLimit-Remaining` / `X-RateLimit-Reset` / 429 status and raises one typed exception. Replaces our hand-rolled `_check_rate_limited(response)` helper. Same observable behavior, no parsing code to maintain.

**Alternatives considered**:
- *Keep the manual header check*: rejected — duplicates gidgethub's work and creates a divergence risk if GitHub changes the header set.

### D5 — Auth token from `settings.github_token` only; no new env vars

**Decision**: Read `settings.github_token` (already wired from `A2WEB_GITHUB_TOKEN`). Pass to `GitHubAPI(oauth_token=...)`. Empty string → unauthenticated (gidgethub handles this).

**Why**: Zero UX change. The existing scenario "Token absence does not block unauthenticated calls" continues to pass unchanged.

### D6 — No pagination beyond what spec scenarios require

**Decision**: For the `next_links` population (top 5 issues + top 5 PRs), use a single `getiter` call with `per_page=5, sort=updated, state=open`. Do not page through all issues.

**Why**: Behavior preserved from the v0.15 handler — it never paged past the first batch. Avoid increasing the cost of a repo URL fetch.

## Risks / Trade-offs

- **[gidgethub API surface evolves and breaks our adapter signature]** → *Mitigation*: pin minor (`gidgethub>=5.4,<6`); the sans-IO interface has been stable since v4. Lock-step upgrades.
- **[gidgethub maintenance momentum could slow]** → *Mitigation*: gidgethub is part of Brett Cannon's ecosystem (one of CPython's core developers). It is small enough that vendoring is a known-cost escape hatch if upstream stalls.
- **[Markdown byte-equivalence regression on edge cases]** → *Mitigation*: snapshot tests cover the three URL shapes. Any byte-difference triggers a deliberate `bless-contracts`-style re-bless or a code-side fix.
- **[A new transport adapter to maintain — yet another piece of glue code]** → *Mitigation*: the adapter is ~30 LoC and has exactly one consumer (this handler). It is dramatically smaller than the code it replaces.
- **[Pagination edge cases that the hand-rolled loop handled but the new path doesn't]** → *Mitigation*: D6 keeps the same scope — we never paged in v0.15 either. If a future requirement needs full pagination, gidgethub's `getiter` already handles it; no adapter change needed.
- **[`Conditional requests` / `If-Modified-Since` were not used in v0.15 and won't be added here]** → *Future opportunity, not a risk*. gidgethub supports them cleanly; revisit when rate-limit pressure justifies the cache complexity.

## Migration Plan

1. Add `gidgethub` to `pyproject.toml`; `uv lock`.
2. Land the `_CurlCffiGitHubTransport` adapter inline in `handlers/github.py` (no removals yet).
3. Refactor `_handle_repo`, `_handle_issue`, `_handle_pull` to use the adapter + gidgethub `getitem`/`getiter`. Keep the markdown renderers unchanged.
4. Switch the rate-limit detection to `except gidgethub.RateLimitExceeded`. Remove the hand-rolled `_check_rate_limited` helper.
5. Delete the hand-rolled URL constructors and pagination helpers.
6. Run snapshot/contract tests for github handler. If any markdown diff appears, decide whether it's an improvement (re-bless) or a regression (fix).
7. Run `make check` + `make handler-probe` against `github.com/octocat/Hello-World`, an issue URL, and a PR URL.
8. Bump version, `make install-global`.

**Rollback**: revert the commit. The transport adapter is removable; the markdown renderers (kept intact) work against either code path.

## Open Questions

- Should we expose a `GITHUB_API_BASE` env var to point at GitHub Enterprise? *Defer* — no demand signal, can be added trivially when asked.
- Should the adapter forward `etag` + `if-none-match` for cache-friendly polling? *Defer* — interesting follow-up once rate-limit pressure justifies the additional state.
- Should we use `gidgethub`'s GraphQL support for the multi-call repo URL path (one GraphQL query vs three REST calls)? *Defer* — REST is simpler, the cost saving is marginal at low traffic, and GraphQL response shape changes would force a formatter rewrite.
