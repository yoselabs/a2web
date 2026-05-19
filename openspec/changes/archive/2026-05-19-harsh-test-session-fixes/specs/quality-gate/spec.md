# quality-gate — paywall + thin-browser rules

## ADDED Requirements

### Requirement: Jina stub recognized as paywall

The quality gate SHALL recognize jina-tier responses carrying upstream-error stubs as `Verdict.paywall` (not `Verdict.length_floor`), so the existing archive escalator can fire. The rule SHALL match responses where ALL of the following hold:

1. The fetch tier is `jina` (recorded on the gate input, not inferred from the body).
2. The body length is below 2,048 characters.
3. The body matches the regex `Target URL returned error 40[13]` (covers both `401 Unauthorized` and `403 Forbidden` — the two jina-stub status codes that indicate paywall / auth).

When the rule matches, the gate SHALL set `verdict = Verdict.paywall` and `subsystem = "jina_stub"`. `suggested_tier` SHALL be left `None` — the orchestrator's existing archive-on-paywall playbook handles the next step.

#### Scenario: NYT-shape jina stub triggers paywall verdict

- **WHEN** the gate evaluates a jina-tier response whose body is `Warning: Target URL returned error 403: Forbidden\n...` and total length is ~500 chars
- **THEN** `verdict == Verdict.paywall`, `subsystem == "jina_stub"`

#### Scenario: 401 Unauthorized stub also triggers paywall

- **WHEN** the gate sees a jina response with `Target URL returned error 401: Unauthorized`
- **THEN** the same paywall verdict fires

#### Scenario: Long jina response is not misclassified

- **WHEN** a jina response succeeds normally (10KB+ markdown body that happens to contain the substring `error 403` in quoted text)
- **THEN** the rule does not fire (body length floor enforces this); verdict follows the normal classifier path

### Requirement: Thin browser response on JS-heavy host downgrades to length_floor

When the fetch tier is `browser` AND the response is HTTP 200 AND the rendered body is <1,024 chars AND the host matches the `JS_HEAVY_HOSTS` set, the gate SHALL emit `verdict = Verdict.length_floor` so the orchestrator continues escalation (typically to archive). The `JS_HEAVY_HOSTS` seed set lives in `src/a2web/packages/quality_gate/` (or wherever the gate lives) and initially contains: `x.com`, `twitter.com`, `instagram.com`, `tiktok.com`, `trendyol.com`, `aliexpress.com`. The set SHALL be exposed for extension via a settings-backed override (`A2WEB_JS_HEAVY_HOSTS` env, comma-separated).

#### Scenario: X.com thin browser response is failed

- **WHEN** the browser tier returns 200 OK with a body of ~480 chars (the X "JavaScript is disabled" stub) for host `x.com`
- **THEN** `verdict == Verdict.length_floor` (escalation continues; orchestrator does not return this as a successful fetch)

#### Scenario: Thin browser response from non-listed host is not downgraded

- **WHEN** the browser tier returns 200 OK with a 500-char body from `someblog.example.com` (not in JS_HEAVY_HOSTS)
- **THEN** the gate uses the normal classifier path; the rule does not fire

#### Scenario: Custom host added via settings override is matched

- **WHEN** `A2WEB_JS_HEAVY_HOSTS="custom.example.com"` is set and the browser tier returns a thin response for that host
- **THEN** the rule fires for `custom.example.com`
