## ADDED Requirements

### Requirement: A handler can escalate to a direct paid site render

A tier result MAY carry an `escalate_to_render` signal. A handler sets it when its optimized route fails (a converting handler's rewritten fetch errors, or a walled surface returns a hard block) but the ORIGINAL URL is still a renderable page. On such a result the orchestrator MUST record the failed attempt as a diagnostic, log a NON-authoritative tier observation (so even a `not_found`/`404` from the handler does not end the run), STOP the free tier ladder (which is fooled by SPA shells that exceed the length floor and by block pages), and dispatch the paid tier (Zyte `browserHtml`) directly onto the original URL. The paid result is then gated like any other tier output. If no paid tier is keyed — or the paid render fails — the fetch MUST surface as retrieval-incomplete with a critical `try_user_browser` operator hint (never-silently-miss), because the free ladder was stopped and the render was the only route.

#### Scenario: Render signal dispatches the paid tier and skips the free ladder

- **WHEN** the site-handler tier returns a result with `escalate_to_render` set for `https://hn.algolia.com/?q=claude`
- **THEN** the orchestrator dispatches the paid tier (Zyte `browserHtml`) on the original URL
- **AND** the free tiers (`raw`, `jina`) are not run
- **AND** on success the paid-rendered content wins the fetch

#### Scenario: A handler placeholder verdict does not end the run

- **WHEN** the handler's `escalate_to_render` result carries verdict `not_found` (e.g. a `404` from a rewritten API)
- **THEN** the observation is recorded as non-authoritative
- **AND** the paid render still proceeds (the `404` does not short-circuit as an authoritative site-handler not_found)

#### Scenario: Render failure is a loud miss

- **WHEN** `escalate_to_render` is requested but no paid tier is keyed (or the paid render fails)
- **THEN** the response has `retrieval_incomplete` set
- **AND** carries a critical `try_user_browser` operator hint
- **AND** does not present the free-tier shell as a successful answer

#### Scenario: The failed attempt is recorded

- **WHEN** a handler escalates via `escalate_to_render`
- **THEN** a diagnostic row for the handler's tier is present in the response (the attempt is observable, not silently dropped)
