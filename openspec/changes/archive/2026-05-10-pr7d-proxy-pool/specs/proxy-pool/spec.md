## ADDED Requirements

### Requirement: Route policy resolves a proxy decision per (host, tier)

The system SHALL provide `resolve_route(host: str, tier: str, settings: AppSettings) -> ResolvedRoute`. The function SHALL be pure (no I/O, no global state). It SHALL scan `settings.routes` in order and return the first match, where match keys are:

- `host`: exact hostname OR `*.glob` (e.g., `*.archive.today` matches `archive.today` and any subdomain)
- `tier`: exact tier name (`"raw"`, `"jina"`, `"archive"`, `"browser"`, or `None` = any)

Match keys compose with AND. A rule with neither key matches everything. When no rule matches, the function SHALL return a `ResolvedRoute` with `proxy_url=None` (direct).

`ResolvedRoute` carries: `proxy_url: str | None`, `proxy_id: str | None`, `proxy_required: bool`, `fallback: list[str]`, `matched_rule_index: int | None`.

ENV variable references in `proxy.url` (e.g., `socks5://user:${PROXY_PASS}@host:1080`) SHALL be resolved at policy time via `os.environ.get`. Missing ENV vars SHALL leave the literal `${VAR}` in place; the operator hint surfaces this on first use.

#### Scenario: Exact host match

- **WHEN** the route table contains `[host="archive.ph", proxy="residential_eu"]` and the resolver is called with `host="archive.ph"`, `tier="raw"`
- **THEN** `ResolvedRoute.proxy_id == "residential_eu"` and `proxy_url` is the resolved URL

#### Scenario: Glob host match

- **WHEN** the route table contains `[host="*.archive.today", proxy="residential_eu"]` and the resolver is called with `host="archive.today"` or `host="foo.archive.today"`
- **THEN** both calls match and return `residential_eu`

#### Scenario: Tier match

- **WHEN** the route table contains `[tier="browser", proxy="datacenter_us"]` and the resolver is called with any host and `tier="browser"`
- **THEN** the result is `datacenter_us`

#### Scenario: Composable AND match

- **WHEN** a rule specifies both `host="archive.ph"` and `tier="raw"` and the resolver is called for that host but `tier="jina"`
- **THEN** the rule does NOT match; resolution falls through

#### Scenario: Explicit direct override

- **WHEN** the table is `[host="*", proxy="residential_eu"]` followed by `[host="reddit.com", proxy="direct"]` and the resolver is called for `reddit.com`
- **THEN** the second rule wins; `proxy_url is None`

#### Scenario: No match defaults to direct

- **WHEN** the route table is empty
- **THEN** `ResolvedRoute.proxy_url is None` and `matched_rule_index is None`

### Requirement: Proxy pool tracks health and fallback chains

The system SHALL provide `ProxyPool` with:

- `acquire(host: str, tier: str) -> ProxyHandle | None` — resolves a route, walks `[primary, *fallback]` in order, returns the first proxy whose health is `alive`. Returns `None` when all proxies in the chain are quarantined or dead AND the rule has `proxy_required=True`. When `proxy_required=False` and all are unhealthy, returns a `ProxyHandle` with `proxy_url=None` (direct).
- `report(handle: ProxyHandle, *, success: bool, ms: int)` — updates per-proxy health. Three consecutive failures SHALL transition `alive → quarantined_until(now + 600s)`. A success while quarantined SHALL transition to `alive`.

The pool's lifecycle mirrors the browser pool: `state.ensure_proxy_pool` opens it lazily under `asyncio.Lock` on first non-direct resolution; the existing atexit hook closes it at process exit.

#### Scenario: Acquire returns first healthy proxy in chain

- **WHEN** the resolved route names primary `p1` (alive), fallback `[p2, p3]`
- **THEN** `acquire` returns a handle for `p1`

#### Scenario: Quarantined primary skipped

- **WHEN** primary `p1` is quarantined and fallback is `[p2 (alive)]`
- **THEN** `acquire` returns a handle for `p2`

#### Scenario: All dead with proxy_required fails

- **WHEN** all proxies in the chain are quarantined or dead AND `proxy_required=True`
- **THEN** `acquire` returns `None`

#### Scenario: All dead without proxy_required falls back to direct

- **WHEN** all proxies are unhealthy AND `proxy_required=False`
- **THEN** `acquire` returns a handle with `proxy_url is None`

#### Scenario: Three consecutive failures quarantine

- **WHEN** `report(handle, success=False)` is called three times consecutively for the same proxy
- **THEN** the proxy's health is `quarantined_until(t)` for `t > now + 599s`
