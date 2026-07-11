# retrieval-completeness Specification

## Purpose
TBD - created by archiving change reddit-reachability-never-silent-miss. Update Purpose after archive.
## Requirements
### Requirement: An unfetched URL is never mistakable for success

Every fetch that ends `status: failed` SHALL be treated as a retrieval miss and prescribe the caller's own browser — EXCEPT a small, explicit set of **genuine-gone** terminals where a browser genuinely cannot help. This is a single systematic floor, not a per-verdict whitelist: the response SHALL carry the critical `try_user_browser` operator hint and `retrieval_incomplete: true` whenever the resolved verdict is not `ok` and is not a genuine-gone terminal. The wire serializer SHALL NOT present such a fetch as a soft, complete-looking answer.

The **genuine-gone terminals** (the only `failed` outcomes that do NOT prescribe a browser) are:

- `dns_error` — the domain does not resolve; a real browser resolves the same name identically. Reported as genuinely unresolvable, NOT `retrieval_incomplete`.
- an **authoritative** `not_found` — a site handler that models the site's real "gone" semantics (a deleted item). Reported as genuinely gone, NOT `retrieval_incomplete`.
- `content_type_mismatch` — a non-HTML resource WAS retrieved (a PDF/image); a browser will not extract it better. Not a wall; no `try_user_browser`.
- `paid_auth_error` — carries its OWN dedicated `paid_auth_error` hint (a keyed paid tier's bad credentials, an operator error) instead of `try_user_browser`; it IS still `retrieval_incomplete`.

Every OTHER failed verdict SHALL prescribe the browser — the content walls (`block_page_detected`, `anti_bot`, `paywall`, `blank_page`), the transport failures (`connection_error`, `timeout`, `rate_limited`, uncorroborated `not_found`), AND the verdicts that fell through the prior whitelists (`length_floor`, `proxy_unavailable`, `other`). A `length_floor` (or any thin/failed terminal) that arises downstream of a wall — e.g. a 403 followed by a thin reader response — SHALL therefore prescribe the browser by construction, without the orchestrator needing to remember which earlier verdict started the cascade. Before any of these terminals is declared, the transport/status walls SHALL still be routed through the escalation ladder (`EscalateBrowser` → archive → `EscalatePaid`), and a `blank_page` through the browser then paid scraper — the ladder is *attempted* exactly as for content-gated walls; the floor is what fires once it is exhausted.

The hint SHALL remain capability-generic (it SHALL NOT name a specific browser product); it prescribes that the caller open the URL in its own real-browser tool (which passes walls that all server-side and headless automation are blocked by) OR explicitly tell the user the source could not be retrieved. Emission SHALL occur once per fetch at a single chokepoint that runs regardless of which internal phase terminated the cascade, and SHALL NOT double-emit when a handler already attached the hint eagerly.

#### Scenario: Any content wall prescribes the browser
- **WHEN** a fetch terminates on `block_page_detected`, `anti_bot`, `paywall`, or `blank_page`
- **THEN** the response carries `retrieval_incomplete: true`, `status: failed`, and the critical `try_user_browser` hint

#### Scenario: A thin terminal downstream of a wall prescribes the browser
- **WHEN** a fetch is refused by an upstream tier (e.g. a 403) and a later tier returns a thin body the gate resolves to `length_floor`, so the fetch ends `failed` with `length_floor`
- **THEN** the response carries `retrieval_incomplete: true` and the critical `try_user_browser` hint — the miss is loud even though `length_floor` was on no prior wall whitelist

#### Scenario: Proxy exhaustion prescribes the browser
- **WHEN** a fetch ends `failed` on `proxy_unavailable` (the proxy pool is exhausted)
- **THEN** the response carries `retrieval_incomplete: true` and the `try_user_browser` hint (the caller's own browser bypasses a2web's proxy entirely)

#### Scenario: A genuinely-gone URL is not dressed as a wall
- **WHEN** a fetch ends on `dns_error` or an authoritative `not_found`
- **THEN** the response is `status: failed` but carries NO `try_user_browser` hint and is NOT `retrieval_incomplete` — it honestly reports the domain/resource as gone, not "behind a wall"

#### Scenario: A retrieved non-HTML resource is not a wall
- **WHEN** a fetch ends on `content_type_mismatch` (a non-HTML resource was retrieved)
- **THEN** the response does NOT carry the `try_user_browser` hint (a browser will not extract it better)

#### Scenario: A bad paid key keeps its own hint
- **WHEN** a fetch ends on `paid_auth_error`
- **THEN** the response carries the dedicated `paid_auth_error` hint (NOT `try_user_browser`) and is `retrieval_incomplete: true`

#### Scenario: The hint is emitted once, at a single chokepoint
- **WHEN** a fetch fails via a bodyless transport path (early-returning before the gate) OR via a body-bearing content wall
- **THEN** the `try_user_browser` hint is emitted exactly once by the same systematic floor, and a handler's eager emission is not duplicated

### Requirement: Critical browser-escalation hint
On a terminal wall verdict, the response SHALL include `OperatorHint(code="try_user_browser")` at `severity: critical` with imperative, capability-generic wording instructing the caller to either open the URL in a real-browser tool OR explicitly tell the user the source could not be retrieved. The hint SHALL NOT name a specific browser product.

#### Scenario: Critical hint on wall
- **WHEN** a fetch terminates on `anti_bot`
- **THEN** a `try_user_browser` critical hint is present with imperative wording and no product-specific tool name

### Requirement: Eager for Reddit, late for unknown walls
For Reddit walled fetches (where the full tier ladder is known to fail), the hint SHALL be emitted eagerly by the handler without spending the browser tier. For other hosts, the hint SHALL be emitted late — only after the tier ladder is exhausted — so tiers with real hit rates are not skipped.

#### Scenario: Reddit emits eagerly
- **WHEN** a Reddit fetch is walled at the handler
- **THEN** the critical hint is emitted without dispatching the browser tier

#### Scenario: Unknown host emits late
- **WHEN** an unknown host is walled at the raw tier
- **THEN** the ladder continues (jina/archive/browser) and the hint is emitted only if all tiers fail

### Requirement: Unrecognized Reddit shape hint
When a Reddit URL matches no supported shape, the handler SHALL emit a hint listing the API-convertible shapes rather than silently falling through.

#### Scenario: Weird Reddit URL gets a breadcrumb
- **WHEN** a Reddit URL of an unrecognized shape is fetched
- **THEN** the response includes a hint naming the supported shapes (thread, permalink, search, top/new listing, user)

### Requirement: Obstacle-flagged ask answers surface as retrieval-incomplete

The never-silently-miss floor SHALL extend to the confabulation case: when an `ask` extractor reports an `obstacle` in `{empty, blocked}` — indicating the page carried no answer-bearing content matching the request (an SPA shell, a stale/unrelated render, or a wall the extractor still summarized) — the orchestrator SHALL FIRST attempt one paid render of the original URL to complete retrieval, provided a paid tier is keyed and no paid render was already spent (`paid_dispatches < 1`). When the render produces new content, the answer is re-extracted over it and the fresh `obstacle` is authoritative.

`retrieval_incomplete = true` (plus a `retrieval_incomplete` operator hint naming the likely cause) MUST be set when the obstacle survives: no paid tier is keyed, the render produced nothing new, or the re-extraction still reports `obstacle ∈ {empty, blocked}`. A fluent-but-unfounded answer with a surviving obstacle MUST NOT be presented as a confident, complete result. `paywalled` / `error` obstacles cap confidence but do NOT trigger a render (a render won't clear a paywall; archive owns that path).

**Structured-grounded carve-out.** An `obstacle: "empty"` SHALL NOT set `retrieval_incomplete` and SHALL NOT emit the critical `retrieval_incomplete` hint when ALL of: (a) the `ok` verdict was promoted by the `structured-data-answers` length-floor exemption (the page was thin and its only answer source was an answer-bearing structured candidate — surfaced as an internal `structured_grounded` signal on the response), AND (b) the extractor returned a **non-empty** answer. In that population a non-empty answer is structured-grounded by construction, so the `empty` obstacle is a false positive. The honest hedge is retained — `confidence` stays `low` for these answers — so the caller is still directed to verify, via a low-confidence answer rather than a klaxon that contradicts the delivered answer. This carve-out applies ONLY to `empty`: a `blocked` obstacle, and any obstacle on a page whose `ok` did NOT come from the structured exemption, keep today's incompleteness behavior. An empty answer is out of scope (the `extraction_empty` guard still hard-fails it).

#### Scenario: Empty obstacle triggers a paid render before declaring incomplete

- **WHEN** an `ask` fetch reports `obstacle: "empty"`, a paid tier is keyed, and `paid_dispatches < 1`
- **THEN** the orchestrator dispatches one paid render of the original URL and re-extracts the answer over the rendered content
- **AND** if the render yields answer-bearing content (fresh obstacle clears), the response is `ok` with the real answer and is NOT flagged incomplete

#### Scenario: Surviving obstacle after render is flagged incomplete

- **WHEN** the paid render produces nothing new, or the re-extraction still reports `obstacle ∈ {empty, blocked}`
- **THEN** the response sets `retrieval_incomplete = true`, carries the `retrieval_incomplete` operator hint, and `confidence` is `low`

#### Scenario: No paid tier keyed still flags incomplete (loud miss)

- **WHEN** an `ask` fetch reports `obstacle: "empty"` but no paid tier is registered
- **AND** the `ok` verdict did NOT come from the structured-answer exemption (a normal prose page)
- **THEN** no render is attempted, and the response sets `retrieval_incomplete = true` with the critical hint (never-silently-miss holds)

#### Scenario: A prior paid render suppresses the obstacle render

- **WHEN** an `ask` fetch already spent its paid dispatch (`paid_dispatches == 1`, e.g. a gate wall or handler `escalate_to_render`) and the extractor still reports `obstacle ∈ {empty, blocked}`
- **THEN** no second paid render is attempted, and the surviving obstacle flags `retrieval_incomplete`

#### Scenario: Paywalled/error obstacles do not trigger a render

- **WHEN** an `ask` fetch reports `obstacle: "paywalled"` or `obstacle: "error"`
- **THEN** no obstacle-driven render is dispatched, and `confidence` is capped to `low` (the wall/verdict machinery owns paywall completeness)

#### Scenario: Structured-grounded non-empty answer is not flagged incomplete

- **WHEN** an `ask` fetch on a thin page was promoted to `ok` by the structured-answer length-floor exemption (`structured_grounded`), the extractor returns a non-empty answer, and reports `obstacle: "empty"`
- **THEN** `retrieval_incomplete` stays `false`, no critical `retrieval_incomplete` hint is emitted, and `confidence` is `low` (the answer is delivered with an honest hedge, not a contradiction)

#### Scenario: Structured-grounded EMPTY answer still hard-fails

- **WHEN** a structured-exemption-promoted page yields an empty answer
- **THEN** the `extraction_empty` guard fires (`status: failed` + `retrieval_incomplete`), unchanged by the carve-out

#### Scenario: The empty-answer guard covers thin promoted pages

- **WHEN** an `ask` on a `structured_grounded` page has `extraction_meta` set but an empty extracted answer, and `content_md` is below the 500-char `extraction_empty` length threshold
- **THEN** `extraction_empty` STILL fires (`status: failed` + `retrieval_incomplete`) — the `>500` threshold, which assumed thin pages already failed at the length floor, is extended with `or structured_grounded` so a promoted thin page cannot return an `ok` empty answer (ADR-0009 never-silently-miss)

#### Scenario: A blocked obstacle on a promoted page is still flagged

- **WHEN** a structured-exemption-promoted page reports `obstacle: "blocked"` (not `empty`)
- **THEN** the carve-out does NOT apply and `retrieval_incomplete = true` with the critical hint

