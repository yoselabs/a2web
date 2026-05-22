## MODIFIED Requirements

### Requirement: Gate result carries optional suggested_tier

`GateResult` SHALL gain a `suggested_tier: str | None = None` field. When a detector fires on an anti-bot signal that maps to a specific escalation tier per the engineering.md §2 signal table, the gate SHALL set `suggested_tier` to the mapped value (`"browser"` or `"tls_impersonate"`). When no signal fires or the verdict is `ok`, `suggested_tier` SHALL be `None`.

The gate SHALL NOT act on this signal and SHALL NOT route escalation. `suggested_tier` is recorded as evidence on the gate's `Observation` in the cascade decision log; the planner `decide_next` — not the gate, and not the orchestrator inline — decides whether and how to escalate (see the `cascade-decision-log` capability).

The signal table for v0.1 is:

| Signal | `suggested_tier` |
|---|---|
| Anubis marker (`anubis` script src or page text) | `browser` |
| Turnstile widget marker (`cf-turnstile`, `turnstile-callback`) | `browser` |
| Akamai BMP sensor markers (`_abck`, `bm_sz`) | `browser` |
| `cf-mitigated: challenge` response header (when surfaced) | `browser` |
| `<noscript>` shell + body < 500 chars + script-heavy | `browser` |
| `cf-chl-bypass` cookie / "Just a moment" interstitial | `tls_impersonate` |

#### Scenario: Anubis page yields suggested_tier = "browser"

- **WHEN** the gate evaluates a response containing the Anubis marker with body length below the floor
- **THEN** `GateResult.verdict == Verdict.anti_bot`, `subsystem == "anubis"`, `suggested_tier == "browser"`

#### Scenario: Cloudflare interstitial yields suggested_tier = "tls_impersonate"

- **WHEN** the gate sees a "Just a moment" interstitial with `cf-chl-bypass` markers
- **THEN** `suggested_tier == "tls_impersonate"`

#### Scenario: Clean article has no suggested_tier

- **WHEN** the gate evaluates a normal article that passes all checks
- **THEN** `verdict == Verdict.ok` and `suggested_tier is None`

#### Scenario: The gate does not itself escalate

- **WHEN** the gate sets `suggested_tier == "browser"`
- **THEN** the gate performs no tier dispatch — it only records the signal as evidence; escalation is left to `decide_next`
