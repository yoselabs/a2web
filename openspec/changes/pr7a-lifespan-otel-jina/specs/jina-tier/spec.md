## ADDED Requirements

### Requirement: Jina tier fetches via r.jina.ai

The system SHALL define `JinaTier` in `src/a2web/tiers/jina.py` implementing the `Tier` protocol with `name = "jina"`. The tier SHALL issue a GET to `https://r.jina.ai/<url>` with header `X-Return-Format: markdown`, including `Authorization: Bearer <key>` only when `state.settings.jina_key` is set. The response body SHALL be wrapped as `tier_extras["pre_rendered"] = {"content_md": <markdown>, "title": None, "byline": None, "headings": []}` so the orchestrator skips trafilatura. `content_type` SHALL be `"text/markdown"`.

#### Scenario: Free-tier call has no Authorization header

- **WHEN** `JinaTier.fetch(url, state=state)` runs with `state.settings.jina_key is None`
- **THEN** the outgoing HTTP request has no `Authorization` header

#### Scenario: Authorized call includes bearer token

- **WHEN** `state.settings.jina_key` is `"secret123"`
- **THEN** the outgoing request carries `Authorization: Bearer secret123`

#### Scenario: Result is pre-rendered

- **WHEN** the tier returns successfully with markdown body `# Hello`
- **THEN** `result.tier_extras["pre_rendered"]["content_md"] == "# Hello"` and the orchestrator's `FetchResponse.content_md` equals the same string (no trafilatura row in diagnostics)

### Requirement: Jina tier respects deny-list

The system SHALL add `jina_deny_hosts: list[str]` to `AppSettings` (default `[]`) and the tier SHALL return a sentinel `TierResult` with `tier_extras["skipped"] = True, "reason": "deny-list"` and `verdict = Verdict.other` when the URL's host (suffix-matched) appears in the deny-list. The orchestrator SHALL skip the diagnostic row for skipped tiers, mirroring the `no_match` pattern.

#### Scenario: Denied host short-circuits

- **WHEN** `jina_deny_hosts == ["intranet.example.com"]` and the URL host is `wiki.intranet.example.com`
- **THEN** `JinaTier.fetch` returns immediately with `tier_extras["skipped"] = True` and no HTTP request is issued

#### Scenario: Skipped tier produces no diagnostic row

- **WHEN** the orchestrator runs against a denied URL
- **THEN** `FetchResponse.diagnostics` contains no entry with `step == "jina"`

### Requirement: TIER_ORDER includes jina after raw

The system SHALL update `TIER_ORDER` in `src/a2web/tiers/__init__.py` to `("site_handler", "raw", "jina")` and register `JinaTier` in `REGISTRY`.

#### Scenario: Cascade order

- **WHEN** the registry is imported
- **THEN** `TIER_ORDER == ("site_handler", "raw", "jina")` and `"jina" in REGISTRY`
