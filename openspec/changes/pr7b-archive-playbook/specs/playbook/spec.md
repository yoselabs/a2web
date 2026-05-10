## ADDED Requirements

### Requirement: Playbook is a pure deterministic action table

The system SHALL define `src/a2web/actions/playbook.py` exporting `Action` (a closed union of `RetryViaArchive`, `RewriteUrl`, `Skip`, all `@dataclass(slots=True)`), and two pure functions:

- `next_action_after_tier(tier_result, url, settings) -> Action | None` — consulted after every tier returns
- `next_action_after_gate(verdict, url, settings) -> Action | None` — consulted after the quality gate runs

Both SHALL be free of I/O, return `None` when no rule matches, and be exhaustively unit-testable. The module SHALL contain no globals beyond a `_RULES` rule list.

#### Scenario: No-op when no rule matches

- **WHEN** `next_action_after_gate(Verdict.ok, url="https://example.com", settings=AppSettings())` is called
- **THEN** the result is `None`

#### Scenario: Module is pure

- **WHEN** static analysis walks `a2web.actions.playbook`
- **THEN** the module imports nothing from `a2web.fetcher`, `a2web.tiers`, or any I/O-bound module (only models, settings, stdlib)

### Requirement: v0.1 playbook rules

The system SHALL implement these rules with the listed precedence (first match wins):

1. **Paywall verdict** → `RetryViaArchive(url=url)` when `next_action_after_gate(Verdict.paywall, url, settings)` is called
2. **Block-page verdict** → `RetryViaArchive(url=url)` for `Verdict.block_page_detected`
3. **HTTP 403/429 from a Cloudflare-fronted host** → `RetryViaArchive` (after-tier rule). A "Cloudflare-fronted host" is any URL whose tier result `tier_extras["server"]` (lowercased) contains "cloudflare", or whose response headers include `cf-ray`.
4. **arxiv.org/pdf/<id>** → `RewriteUrl(new_url="https://arxiv.org/abs/<id>")` (after-tier rule, fires regardless of verdict; PR8's arxiv handler will pick up the abs page)

#### Scenario: Paywall triggers archive

- **WHEN** `next_action_after_gate(Verdict.paywall, "https://nyt.com/article", AppSettings())` is called
- **THEN** the result is `RetryViaArchive(url="https://nyt.com/article")`

#### Scenario: Cloudflare 403 triggers archive

- **WHEN** a tier result has `status_code=403`, `headers={"cf-ray": "abc"}`, and `next_action_after_tier(result, url, settings)` is called
- **THEN** the result is `RetryViaArchive(url=url)`

#### Scenario: arxiv pdf rewrite

- **WHEN** the URL is `https://arxiv.org/pdf/2401.12345` and any after-tier rule runs
- **THEN** the result is `RewriteUrl(new_url="https://arxiv.org/abs/2401.12345")`
