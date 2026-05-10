## ADDED Requirements

### Requirement: Orchestrator escalates to archive on gate verdict

The orchestrator SHALL call `next_action_after_gate(verdict, url, settings)` after the quality gate runs. When the action is `RetryViaArchive(url=u)`, the orchestrator SHALL invoke `REGISTRY["archive"].fetch(u, state=state)` immediately, replace the body/content_md/headings with the archive result's pre-rendered payload, mark `tier_used = "archive"`, and re-evaluate the gate against the archive content. The escalation SHALL fire at most once per fetch.

#### Scenario: Paywall on raw triggers archive dispatch

- **WHEN** raw returns `Verdict.ok`, the gate yields `Verdict.paywall`, and `next_action_after_gate` returns `RetryViaArchive`
- **THEN** the orchestrator dispatches the archive tier and the resulting `FetchResponse.tier == "archive"` on success

#### Scenario: Second escalation skipped

- **WHEN** the gate verdict on the archive content also triggers `RetryViaArchive`
- **THEN** no further archive dispatch occurs (cap of 1 per fetch)

### Requirement: After-tier playbook actions deferred (PR7b)

For PR7b, the orchestrator SHALL call `next_action_after_tier` and record any returned action under `tier_extras["pending_action"]` for diagnostics, but SHALL NOT act on `RewriteUrl` or after-tier `RetryViaArchive`. Implementation lands in PR7c alongside the proxy-pool retry layer.

#### Scenario: Pending action recorded, not executed

- **WHEN** `next_action_after_tier` returns `RewriteUrl(new_url="x")`
- **THEN** the orchestrator does not restart the tier loop; the action is dropped (PR7c will execute it)

### Requirement: Archive results skip cache write

The orchestrator SHALL skip the cache write when `tier_result.tier_extras.get("from_archive") is True`, regardless of verdict.

#### Scenario: Archive hit not cached

- **WHEN** the archive tier returns `Verdict.ok` with `tier_extras["from_archive"] = True`
- **THEN** no row is inserted into the `cache` table for the URL+profile_hash key
