## ADDED Requirements

### Requirement: HN Algolia search handler matches and routes via the search API

The Hacker News handler SHALL claim `hn.algolia.com` search-UI URLs (`hn.algolia.com/?q=<query>`) in addition to `news.ycombinator.com` front-page and item URLs, and SHALL resolve them by calling the Algolia search API (`https://hn.algolia.com/api/v1/search?query=<query>&tags=story&hitsPerPage=30`) directly rather than rendering the client-side SPA. The rendered result MUST reuse the same hit-list rendering and next-link discovery used for the HN front page.

#### Scenario: Algolia search UI URL is claimed by the HN handler

- **WHEN** `match_handler` is asked to resolve `https://hn.algolia.com/?q=claude%20code`
- **THEN** the HN handler's `matches()` returns true (the URL is not left for the generic tier ladder)

#### Scenario: Search UI URL resolves via the Algolia search API

- **WHEN** the HN handler fetches `https://hn.algolia.com/?q=claude%20code`
- **THEN** it issues a GET to `https://hn.algolia.com/api/v1/search?query=claude%20code&tags=story&hitsPerPage=30`
- **AND** returns a `TierResult` with `verdict == ok`, `pre_rendered` content listing the story hits (title + points), and populated `next_links` to the discussion pages

#### Scenario: Empty query is not claimed

- **WHEN** `match_handler` is asked to resolve `https://hn.algolia.com/` with no `q` parameter
- **THEN** the HN handler's `matches()` returns false (no search intent to route)

#### Scenario: HN escalates to a paid site render when the Algolia API fails

- **WHEN** the HN handler's rewritten Algolia API fetch fails (non-2xx, or an unparseable body)
- **THEN** the returned `TierResult` carries `escalate_to_render` set, so the orchestrator renders the original URL via the paid tier instead of surfacing the API's transport error

#### Scenario: A successful HN search does not escalate to render

- **WHEN** the HN handler's Algolia API fetch succeeds
- **THEN** the returned `TierResult` does not set `escalate_to_render` (the handler's rendered result wins)
