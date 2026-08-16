# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report privately through GitHub's private vulnerability reporting:
[**Report a vulnerability**](https://github.com/yoselabs/a2web/security/advisories/new)
(repo → **Security** → **Advisories** → **Report a vulnerability**). The
report is visible only to the maintainers until a fix is published.

Useful in a report: affected version, the URL or input that triggers it,
what an attacker gains, and a minimal reproduction. A rough report beats a
silent one — send it even if you can't complete the picture.

## What to expect

| Stage | Target |
| --- | --- |
| Acknowledgement | within 3 business days |
| Initial assessment (is it real, how bad) | within 7 days |
| Fix or a stated plan | depends on severity — communicated in the assessment |

Best-effort targets, not an SLA: a2web is maintained by one person. If you
get no acknowledgement in a week, please ping the advisory thread again.

Reporters are credited in the published advisory unless you'd rather not be.

## Scope

Fixes land on the latest released version only (see `CHANGELOG.md`); there
are no maintained back-branches.

a2web fetches and parses attacker-controlled web content, so these are in
scope and worth reporting:

- Fetched page content escaping its data role — reaching code execution,
  the filesystem, or the host through a parser, renderer, or the browser tier.
- SSRF beyond the requested URL: a page steering a2web at an internal
  address or a `file://`-class target.
- Leaking configured secrets (`A2WEB_*` tokens, cookies, LLM credentials)
  into responses, logs, caches, or feedback telemetry.
- Prompt injection in fetched content that makes a2web act outside relaying
  content — issuing further fetches or writes the caller never asked for.

Out of scope: findings against third-party services a2web calls (report
those to the service), volumetric denial of service, and missing hardening
with no demonstrated impact.
