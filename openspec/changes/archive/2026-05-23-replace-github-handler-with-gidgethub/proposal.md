## Why

`src/a2web/handlers/github.py` is 435 LoC, of which roughly half is hand-rolled REST plumbing: URL → endpoint construction, pagination, auth-header attachment, rate-limit decoding, and base64-README unwrapping. `gidgethub` is the de facto sans-IO GitHub API library — it owns no transport, so it slots into our existing curl_cffi tier and inherits our retries, breakers, proxy routing, and cookie jar for free. Outsourcing this plumbing shrinks the handler to its actual job (markdown formatting from typed objects), eliminates an entire class of "did we encode the URL right / decode the rate-limit header right" bugs, and tracks GitHub API evolution upstream.

## What Changes

- Add `gidgethub>=5.4,<6` as a direct dependency.
- Replace hand-rolled GitHub REST calls in `src/a2web/handlers/github.py` with `gidgethub.sansio.GitHubAPI` driven through a thin curl_cffi-backed transport adapter. The adapter SHALL live inline in `handlers/github.py` (small enough — ~30 LoC) and SHALL NOT introduce a new `packages/` module.
- Preserve every observable behavior of the v0.15 handler: same URL shapes matched, same markdown output, same `verdict == Verdict.rate_limited` on 429 / `X-RateLimit-Remaining: 0`, same `A2WEB_GITHUB_TOKEN` → `Authorization: Bearer ...` semantics, same `TierResult.next_links` population on repo URLs (top 5 issues + top 5 PRs).
- Remove the hand-rolled pagination loop, the manual `Link:` header parser, the manual rate-limit-header decode, and the manual base64-README unwrap (gidgethub does all four).
- Keep the markdown rendering functions in `handlers/github.py` unchanged — they consume the parsed dicts gidgethub returns. Pure formatter code stays.

Not changing: the `Handler` protocol, the handler registration in `handlers/__init__.py`, the `TierResult` shape, or any MCP wire surface.

## Capabilities

### New Capabilities

None — pure refactor.

### Modified Capabilities

- `site-handlers`: the `github handler renders repo / issue / pull URLs` requirement and the `GitHub repo handler populates issue/pull candidates` requirement remain in force; their scenarios are unchanged. The implementation-level note that "the handler calls the corresponding GitHub REST API endpoint(s)" is reinterpreted as "via gidgethub". Tests written against the scenarios pass without modification.

## Impact

- **Code**: `src/a2web/handlers/github.py` shrinks from 435 LoC to roughly 230-260 LoC (markdown formatters + thin transport adapter + dispatch). Net ~150-180 LoC out.
- **Dependencies**: `+gidgethub` (sans-IO, pure Python, no transport bloat — depends only on `uritemplate` + stdlib).
- **HTTP path**: every GitHub API request continues to flow through curl_cffi → our breakers → our proxy routing. gidgethub never owns a socket; the transport adapter does.
- **Tests**: existing `tests/handlers/test_github.py` continues to drive against the same fixtures; the monkeypatch surface shifts from `httpx`-shaped fakes to a `GitHubAPI._request`-shaped fake. Scenarios in the spec are unchanged.
- **`packages/` rule**: not impacted — the transport adapter lives in `handlers/github.py` (domain), not in `packages/`. gidgethub is third-party, not an `a2web.<domain>` import.
- **MCP wire surface**: no change. `pre_rendered.content_md` byte-equivalence is the contract; same markdown formatter functions produce the same bytes.
- **Rate-limit behavior**: `gidgethub.RateLimitExceeded` exception maps to `verdict == Verdict.rate_limited` — same observable outcome, cleaner trigger path.
