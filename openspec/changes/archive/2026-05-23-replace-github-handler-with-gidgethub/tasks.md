## 1. Dependency

- [ ] 1.1 Add `gidgethub>=5.4,<6` to `pyproject.toml` `[project] dependencies`. Run `uv lock`. Confirm transitive deps (`uritemplate`) are pure-Python and small.

## 2. Transport adapter

- [ ] 2.1 In `src/a2web/handlers/github.py`, add `_CurlCffiGitHubTransport` (~30 LoC). It SHALL accept the existing curl_cffi session as a constructor kwarg and expose the request method that `gidgethub.sansio.GitHubAPI` calls (`requester` shape).
- [ ] 2.2 Adapter sets the gidgethub-mandated headers (`User-Agent`, `Accept: application/vnd.github+json`). Treats the curl_cffi response bytes as the gidgethub response body. Surfaces non-2xx via gidgethub's standard exception path (so `RateLimitExceeded` fires correctly on 429 / 403 + `X-RateLimit-Remaining: 0`).
- [ ] 2.3 Add a unit test that confirms the adapter executes a fake `getitem` against a stubbed curl_cffi session and that response bytes flow through unchanged.

## 3. Replace REST plumbing

- [ ] 3.1 In `_handle_repo`: replace hand-rolled `/repos/...` and `/repos/.../readme` calls with `await gh.getitem("/repos/{owner}/{repo}")` and `await gh.getitem("/repos/{owner}/{repo}/readme")`. Drop manual base64 unwrap — gidgethub returns decoded content.
- [ ] 3.2 In `_handle_issue`: replace with `await gh.getitem("/repos/{owner}/{repo}/issues/{n}")` + `gh.getiter("/repos/{owner}/{repo}/issues/{n}/comments")`.
- [ ] 3.3 In `_handle_pull`: replace with `await gh.getitem("/repos/{owner}/{repo}/pulls/{n}")` + `gh.getiter` for reviews and comments.
- [ ] 3.4 For repo URL `next_links`: replace hand-rolled top-issues / top-pulls fetch with two `getiter` calls (`per_page=5, sort=updated, state=open`). First batch only.
- [ ] 3.5 Delete the hand-rolled URL constructors, the `_check_rate_limited(response)` helper, the manual `Link:` header pagination parser, and the manual base64 README decoder.

## 4. Rate limit + auth

- [ ] 4.1 Wrap each `_handle_*` body in `try / except gidgethub.RateLimitExceeded:` returning `verdict == Verdict.rate_limited` + the existing operator hint mentioning `A2WEB_GITHUB_TOKEN`.
- [ ] 4.2 Construct `GitHubAPI(oauth_token=settings.github_token or None)`. Confirm empty-string token → unauthenticated path.

## 5. Markdown formatters

- [ ] 5.1 Leave `_render_repo_md`, `_render_issue_md`, `_render_pull_md` signatures unchanged. They keep consuming `dict`s — gidgethub returns `dict`s from `getitem` / `getiter`.
- [ ] 5.2 Re-run snapshot/contract tests. Any byte-difference in rendered markdown is a deliberate decision point: either fix the formatter to match the v0.15 byte sequence, or re-bless via `make bless-contracts` after diff review.

## 6. Tests

- [ ] 6.1 Update `tests/handlers/test_github.py` monkeypatch surface. Where it previously stubbed `httpx.AsyncClient.get`, stub gidgethub's `GitHubAPI._request` (or the transport adapter's request method, whichever ends up cleaner).
- [ ] 6.2 Add a test that confirms `RateLimitExceeded` from gidgethub maps to `verdict == Verdict.rate_limited`.
- [ ] 6.3 Add a test that confirms no `httpx`/`aiohttp` socket is opened during a GitHub fetch (asserting the curl_cffi adapter is the only transport in use).
- [ ] 6.4 Confirm `tests/contracts/` passes without re-bless (markdown byte-equivalence).
- [ ] 6.5 Confirm `tests/test_packages_independence.py` continues to pass.

## 7. Verification

- [ ] 7.1 Run `make check` (lint + ty + test-cov ≥85%). All green.
- [ ] 7.2 Run `make handler-probe` — confirm github handler hits `api.github.com/octocat/Hello-World`, an issue URL, and a PR URL, and produces markdown matching the snapshot.
- [ ] 7.3 Manually fetch a real repo URL through Claude Code MCP. Confirm rendered markdown matches v0.15 baseline.

## 8. Ship

- [ ] 8.1 Bump version in `pyproject.toml`.
- [ ] 8.2 Update `CHANGELOG.md` with: removed (~150-180 LoC of hand-rolled GitHub REST plumbing), added (gidgethub direct dep + transport adapter), preserved (markdown output byte-equivalence, all spec scenarios).
- [ ] 8.3 Run `make install-global`.
- [ ] 8.4 Archive this change via the openspec workflow.
