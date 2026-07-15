## MODIFIED Requirements

### Requirement: An unfetched URL is never mistakable for success

Every fetch that ends `status: failed` SHALL be treated as a retrieval miss and prescribe the caller's own browser — EXCEPT the terminals that `classify_terminal` resolves to `gone_confirmed`, `unreachable`, `operator_error`, `thin_unverified`, or `empty_unverified`, where the CRITICAL browser prescription is not warranted. This remains a single systematic floor, expressed as the output of `classify_terminal(observations, resolved_verdict)` (not a whitelist over the resolved verdict): the response SHALL carry the critical `try_user_browser` hint and `retrieval_incomplete: true` exactly when the outcome is `wall`.

The outcomes that do NOT prescribe the critical browser hint are:

- `unreachable` — `dns_error` (the domain does not resolve) or `content_type_mismatch` (a non-HTML resource WAS retrieved). Reported as genuinely unreachable/retrieved-non-HTML, NOT a wall.
- `gone_confirmed` — a handler-authoritative `not_found`, OR an HTTP 404 a browser render corroborated. Reported honestly as gone/dead, NOT `retrieval_incomplete`, with a `content_not_found` info hint rather than `try_user_browser`.
- `operator_error` — `paid_auth_error` keeps its own dedicated hint; it IS still `retrieval_incomplete`.
- `thin_unverified` — a retrieved 200 that rendered thin with NO hard-wall evidence and NO empty-result marker anywhere in the log (genuinely ambiguous: an empty result set OR an unfingerprinted wall). Reported with a `content_thin` WARNING and the retrieved body attached, worded AGNOSTICALLY (it does NOT assert "most likely empty"); NOT the CRITICAL `try_user_browser`.
- `empty_unverified` — a retrieved 200 that rendered thin WITH an empty-result marker but whose promotion conjunction did not hold (see "Corroborated empty is promoted to ok"). Reported with a `content_thin` WARNING that MAY lean empty, and the retrieved body attached; NOT the CRITICAL `try_user_browser`.

`gone_unverified` (an HTTP 404 whose soft-404 check could not complete) is `retrieval_incomplete` but carries the `content_not_found` WARNING (with the browser escape hatch), NOT the CRITICAL `try_user_browser`. Every `wall` outcome — the content walls (`block_page_detected`, `anti_bot`, `paywall`, `blank_page`), a fetch carrying subresource-block evidence (see "Subresource-block evidence is a wall"), and the transport terminals that are not classified gone/unreachable/operator/thin/empty (`connection_error`, `timeout`, `rate_limited`, `proxy_unavailable`, `other`) — SHALL prescribe the browser after the escalation ladder is exhausted. `length_floor` is NO LONGER unconditionally a wall: it is corroboration-keyed (see "Thin is corroboration-keyed, not wall-by-default"). Emission SHALL occur once per fetch at the single chokepoint that consumes `classify_terminal`, and SHALL NOT double-emit when a handler attached a hint eagerly.

#### Scenario: Any content wall prescribes the browser

- **WHEN** a fetch terminates on `block_page_detected`, `anti_bot`, `paywall`, or `blank_page` (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true`, `status: failed`, and the critical `try_user_browser` hint

#### Scenario: A dead URL is reported gone, not walled

- **WHEN** a fetch ends on a corroborated HTTP 404 (outcome `gone_confirmed`)
- **THEN** the response is `status: failed` with a `content_not_found` info hint, NO `try_user_browser`, and NOT `retrieval_incomplete`

#### Scenario: A thin terminal downstream of a wall prescribes the browser

- **WHEN** a fetch is refused by an upstream tier (e.g. a 403 gating `anti_bot`/`block_page_detected`) and a later tier returns a thin body the gate resolves to `length_floor` — hard-wall evidence IS present in the log (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true` and the critical `try_user_browser` hint

#### Scenario: A thin 200 with no wall evidence is not dressed as a wall

- **WHEN** a fetch retrieves an HTTP 200 that renders thin (`length_floor`) after the browser escalation ladder ran, with NO hard-wall gate observation and NO subresource-block evidence and NO empty-result marker anywhere in the log and no `not_found` (outcome `thin_unverified`)
- **THEN** the response is `status: failed` with a `content_thin` hint at `severity: warning`, worded agnostically (could be empty OR an unfingerprinted wall), the retrieved thin body attached, and NO `try_user_browser` critical hint

#### Scenario: Proxy exhaustion prescribes the browser

- **WHEN** a fetch ends `failed` on `proxy_unavailable` with no gone/unreachable evidence (outcome `wall`)
- **THEN** the response carries `retrieval_incomplete: true` and the `try_user_browser` hint (the caller's own browser bypasses a2web's proxy entirely)

#### Scenario: A genuinely-gone URL is not dressed as a wall

- **WHEN** a fetch ends on `dns_error` (outcome `unreachable`) or an authoritative `not_found` (outcome `gone_confirmed`)
- **THEN** the response is `status: failed` but carries NO `try_user_browser` hint and is NOT `retrieval_incomplete` — it honestly reports the domain/resource as gone, not "behind a wall"

#### Scenario: A retrieved non-HTML resource is not a wall

- **WHEN** a fetch ends on `content_type_mismatch` (outcome `unreachable` — a non-HTML resource was retrieved)
- **THEN** the response does NOT carry the `try_user_browser` hint (a browser will not extract it better)

#### Scenario: A bad paid key keeps its own hint

- **WHEN** a fetch ends on `paid_auth_error` (outcome `operator_error`)
- **THEN** the response carries the dedicated `paid_auth_error` hint (NOT `try_user_browser`) and is `retrieval_incomplete: true`

#### Scenario: The hint is emitted once, at a single chokepoint

- **WHEN** a fetch fails via a bodyless transport path OR a body-bearing content wall
- **THEN** the terminal hint is emitted exactly once by the `classify_terminal` chokepoint, and a handler's eager emission is not duplicated

### Requirement: Terminal outcome is a pure projection of the decision log

The caller-facing terminal signals (`retrieval_incomplete`, the wall/gone/error/thin hint, and its `severity`) SHALL be derived by a single pure function `classify_terminal(observations, resolved_verdict) -> TerminalOutcome` that reads the **observation log**, not merely the resolved verdict projection. `TerminalOutcome` SHALL be a closed enum: `wall`, `gone_confirmed`, `gone_unverified`, `thin_unverified`, `empty_unverified`, `operator_error`, `unreachable`. The function SHALL be pure, total, and free of I/O — the terminal-story sibling of the forward planner. It replaces the prior `_is_genuine_gone` / `_prescribe_browser_on_wall` predicate pair.

Because it reads the log, evidence recorded by any tier (e.g. two independent tiers observing HTTP 404, a hard-wall gate outcome that preceded a marker-less thin regate, OR subresource-block evidence a browser observed during render) SHALL be reachable to the classifier even when the *resolved* verdict or the *last* gate differs — the failure mode where a corroborating observation existed but a predicate keyed on the projection could not see it SHALL NOT recur.

#### Scenario: Corroborating observations are reachable

- **WHEN** the log holds `raw: not_found (404)` and `browser: not_found (404)` but the resolved verdict is some other value (e.g. a mis-won thin tier)
- **THEN** `classify_terminal` returns `gone_confirmed` from the corroborated 404 observations, not a `wall` derived from the resolved verdict

#### Scenario: Total over outcomes

- **WHEN** `classify_terminal` is evaluated over the space of observation shapes
- **THEN** every input maps to exactly one `TerminalOutcome`

### Requirement: Hint severity encodes retrieval confidence

`OperatorHint.severity` SHALL carry a confidence semantics: `info` = a verified fact (e.g. a browser-corroborated gone URL, or a promoted-`ok` corroborated empty result), `warning` = the check could not be completed OR the outcome is genuinely ambiguous with the evidence in hand (residual uncertainty the caller may resolve — a soft-404 `content_not_found`, a `content_thin` empty-vs-minimal page, or an `empty_unverified` uncorroborated empty), `critical` = every recovery path was attempted and a wall was hit. A dead URL SHALL NOT receive a `critical` signal, and a retrieved thin 200 with no hard-wall evidence (`thin_unverified` / `empty_unverified`) SHALL NOT receive a `critical` signal.

#### Scenario: A dead URL is never critical

- **WHEN** a fetch terminates on a corroborated or unverified `not_found`
- **THEN** no `critical` hint is emitted; the severity is `info` or `warning` respectively

#### Scenario: A thin 200 with no wall evidence is never critical

- **WHEN** a fetch terminates on `thin_unverified` or `empty_unverified`
- **THEN** no `critical` hint is emitted; the `content_thin` hint is at `severity: warning`

### Requirement: Thin is corroboration-keyed, not wall-by-default

A retrieved page that renders thin (`length_floor`) SHALL be classified by what the cascade OBSERVED across the WHOLE decision log, not by the last gate outcome alone. The cascade already escalates a thin body to the browser (fast Chromium then robust CDP) via the planner's thin-escalation rule, so by the terminal a real headless browser has typically rendered the page and it is still thin — a corroborated thin observation, not an untested ambiguity.

- A `length_floor` last-gate outcome with a hard-wall gate observation (`anti_bot`, `block_page_detected`, `paywall`, or `blank_page`) ANYWHERE in the log → `wall`: the thin page sits downstream of positive wall evidence (e.g. a browser that failed to solve a Turnstile challenge and landed on a bespoke marker-less stub). Keying on the *last* gate alone SHALL NOT downgrade this — the whole log is scanned.
- A thin outcome with **subresource-block evidence** anywhere in the log → `wall` (see "Subresource-block evidence is a wall"): the browser watched a page XHR/fetch get challenged (401/403/429) even though the rendered body reads benign — the walled-API fake-empty. This positive, non-text evidence outranks the empty-marker.
- A `length_floor` last-gate outcome with NO hard-wall evidence, NO subresource-block evidence, and an **empty-result marker** (`subsystem="empty_result"`) but whose promotion conjunction did not hold → `empty_unverified`: leans empty, `severity: warning`, body attached.
- A `length_floor` last-gate outcome with NONE of the above and no `not_found` → `thin_unverified`: genuinely ambiguous (empty result set OR an unfingerprinted wall / an IP-reputation wall serving a bespoke thin body that a2web's same-egress browser could not rule out). Reported at `severity: warning`, worded agnostically, with the retrieved body attached, NOT the CRITICAL wall klaxon.

The retrieved thin body SHALL be attached to the failure envelope so the calling agent can resolve empty-vs-wall itself (ADR-0015: never withhold without leaving the index). No LLM answer SHALL be generated for a `thin_unverified` / `empty_unverified` page — the raw sub-floor body is handed over rather than distilled (ADR-0017: effort ∝ existence prior). The attached body is wire-only and SHALL NOT enter the cache (the never-cache-block-pages invariant is preserved).

#### Scenario: Thin downstream of a hard wall stays a wall (whole-log scan)

- **WHEN** the log holds an early `anti_bot` gate observation, then a browser render whose regate is a marker-less `length_floor` (the last gate)
- **THEN** `classify_terminal` returns `wall` (the hard-wall evidence is found by scanning the whole log, not the last gate), and the critical `try_user_browser` hint is emitted

#### Scenario: Thin 200 with a clean log is thin_unverified

- **WHEN** the log holds only `ok`/`length_floor` gate outcomes across raw → jina → browser with no hard-wall verdict, no subresource-block evidence, and no empty-result marker anywhere and no `not_found`
- **THEN** `classify_terminal` returns `thin_unverified`, the `content_thin` WARNING is emitted with agnostic wording, and the retrieved thin body is attached

#### Scenario: Thin 200 with an empty marker but weak corroboration is empty_unverified

- **WHEN** the log holds a `length_floor` gate outcome annotated `subsystem="empty_result"` but the promotion conjunction fails (e.g. no jina corroboration)
- **THEN** `classify_terminal` returns `empty_unverified`, the `content_thin` WARNING is emitted (may lean empty), and the body is attached — still `status: failed`, NO `try_user_browser`

#### Scenario: The thin body is handed over, not distilled

- **WHEN** a `query` fetch terminates on `thin_unverified` or `empty_unverified`
- **THEN** no LLM answer extraction is run over the sub-floor body, and the retrieved body rides the response wire (even though `query` normally withholds content)

## ADDED Requirements

### Requirement: Subresource-block evidence is a wall

A fetch whose decision log carries subresource-block evidence — a browser tier observation recording that ≥1 page subresource (an XHR/fetch request) returned a challenge status (401/403/429) during render — SHALL classify as `wall`, regardless of how benign the rendered body reads. This is the walled-API fake-empty: an SPA shell 200s and renders an authentic "0 results" template because the data API behind it was blocked. The evidence is non-text and adversary-hard; no body-text reader (regex or LLM) can substitute for it. Subresource-block evidence SHALL outrank the empty-result marker and SHALL block promotion to `ok`.

The browser backend SHALL count subresource challenge responses best-effort (never raising) and surface the count as `RenderedPage.subresource_blocks`; the browser tier SHALL carry it onto its `TierResult` (a typed field, never a `tier_extras` bag); the fetcher SHALL record it on the browser `tier_outcome` Observation.

#### Scenario: A rendered "0 results" whose data API was blocked is a wall

- **WHEN** the browser renders a page with a benign body but its `render` recorded ≥1 XHR/fetch response with status 403 during load (subresource-block evidence)
- **THEN** `classify_terminal` returns `wall` and the critical `try_user_browser` hint is emitted — even if an empty-result marker also matched

#### Scenario: No subresource blocks does not manufacture a wall

- **WHEN** a browser render records zero subresource-block responses
- **THEN** subresource evidence does NOT push the outcome to `wall` (the other classifier rules decide)

### Requirement: Corroborated empty is promoted to ok

A retrieved page that renders thin SHALL be promoted to `status: ok` with "no results" as the answer ONLY when a pure predicate `is_confirmed_empty(observations, url) -> bool` holds — the promotion conjunction, evaluated at the orchestrator's verdict phase BEFORE `classify_terminal` (which is a failure-only taxonomy). All of the following MUST hold:

1. an independent BROWSER render read the page as empty too — a regate gate outcome carrying the empty-result marker (`subsystem="empty_result"`). Corroboration is by the browser, NOT a foreign-egress reader: a thin HTTP 200 wins the tier loop, so the free `jina` rung never runs on it; the browser escalation is the second independent retrieval a thin page actually gets, and it is the stronger corroborator here because it also watched every subresource (term 4);
2. an HTTP `tier_outcome` independently returned a body (`verdict == ok`);
3. NO observation carries a `status_code` in {401, 403, 429} anywhere in the log;
4. NO subresource-block evidence anywhere in the log;
5. NO hard-wall gate evidence anywhere in the log;
6. the URL is search-shaped (`is_search_shaped(url)`).

On promotion the response is `status: ok`, NOT `retrieval_incomplete`, carries a `content_empty` hint at `severity: info`, and the `query` answer is a synthetic honest statement that the page reports no results, at `confidence: low`, with the retrieved body still attached. The promoted-empty response SHALL NOT enter the cache (a wrongly-promoted empty served from cache is a repeating silent miss). When ANY conjunction term fails, the fetch SHALL NOT be promoted and falls to `classify_terminal` (`empty_unverified` when the marker is present, else `thin_unverified` / `wall`).

#### Scenario: A corroborated empty search is promoted to ok

- **WHEN** a search-shaped URL returns a thin body matching an empty-result marker over HTTP AND an independent browser render reads it as empty too (a regate carrying the marker), with no 4xx/challenge status and no subresource-block evidence and no hard-wall evidence anywhere
- **THEN** `is_confirmed_empty` holds, the response is `status: ok` with a synthetic "no results" answer at `confidence: low`, a `content_empty` info hint, the body attached, NOT `retrieval_incomplete`, and NOT cached

#### Scenario: A thin body behind a 403 is never promoted (wall wins)

- **WHEN** an empty-result marker matches but the log holds a 403 status anywhere (raw refused, or a subresource was blocked)
- **THEN** `is_confirmed_empty` is false, no promotion occurs, and the fetch classifies as `empty_unverified` (or `wall` when a subresource block is present)

#### Scenario: A non-search URL is never promoted

- **WHEN** an empty-result marker matches on a non-search route (e.g. an article path) with otherwise-clean corroboration
- **THEN** `is_confirmed_empty` is false (the search-shape term fails) and the fetch classifies as `empty_unverified`, not promoted

#### Scenario: Missing browser corroboration blocks promotion

- **WHEN** an empty-result marker matches on the HTTP retrieval but no browser render corroborated it (the browser was unavailable, so no regate-empty is in the log)
- **THEN** `is_confirmed_empty` is false and the fetch classifies as `empty_unverified` (failed), never promoted on the HTTP read alone
