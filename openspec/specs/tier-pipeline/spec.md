# tier-pipeline Specification

## Purpose
TBD - created by archiving change pr3-raw-tier. Update Purpose after archive.
## Requirements
### Requirement: Tier protocol

The system SHALL define `Tier` as a `typing.Protocol` in `src/a2web/tiers/__init__.py` with members `name: str` and `async def fetch(self, url: str, *, state: AppState) -> TierResult`. `TierResult` SHALL be a `@dataclass(slots=True)` carrying at minimum: `body: bytes`, `content_type: str`, `status_code: int`, `final_url: str`, `headers: dict[str, str]`, `tier_extras: dict[str, Any]` (default empty), `verdict: Verdict` (default `Verdict.ok`). Tiers MUST NOT raise for routine HTTP failures (4xx/5xx) — they SHALL set `verdict` to the closed-enum value (`connection_error`, `timeout`, `rate_limited`, `not_found`, etc.) and return.

#### Scenario: Tier protocol shape

- **WHEN** static analysis walks `a2web.tiers.__init__`
- **THEN** `Tier` is a `Protocol`, `TierResult` is a `@dataclass(slots=True)`, and both are at module scope

#### Scenario: HTTP error becomes a verdict, not an exception

- **WHEN** a tier encounters a 503 from the upstream host
- **THEN** the tier returns a `TierResult` with `verdict in {Verdict.rate_limited, Verdict.connection_error}`, NOT a raised exception

### Requirement: Tier registry with explicit ordering

The system SHALL expose `TIER_ORDER: tuple[str, ...]` and `REGISTRY: dict[str, Tier]` from `a2web.tiers.__init__`. PR3 SHALL register exactly one tier (`"raw"`). The orchestrator SHALL iterate `TIER_ORDER` in sequence and stop at the first tier whose post-gate verdict is `Verdict.ok`.

#### Scenario: Single registered tier in PR3

- **WHEN** the registry is imported in PR3
- **THEN** `len(REGISTRY) == 1` and `TIER_ORDER == ("raw",)`

### Requirement: Block pages never enter the cache

The system SHALL run the quality gate after extraction and before any cache write. If the gate verdict is anything other than `Verdict.ok`, the cache write SHALL be skipped and the verdict SHALL be appended to `FetchResponse.diagnostics`.

#### Scenario: Block page is not cached

- **WHEN** the orchestrator processes a response that triggers any block-page regex
- **THEN** no row is inserted into the `cache` table for the URL+profile_hash key

#### Scenario: Failed-status fetch is not cached

- **WHEN** the orchestrator yields `FetchResponse.status == FetchStatus.failed`
- **THEN** no cache row is written

### Requirement: Adaptive duration formatter

The system SHALL define `fmt_dur(ms: int) -> str` in `src/a2web/utils/time.py`. Output rules:

- `ms < 1000` → `"{ms}ms"` (integer)
- `1000 ≤ ms < 7000` → `"{s:.1f}s"` (one decimal)
- `7000 ≤ ms < 60_000` → `"{s}s"` (integer)
- `ms ≥ 60_000` → `"{m}m{s:02d}s"`

Every duration string in the envelope, diagnostics narrative, and operator hints SHALL be produced via `fmt_dur`. Hand-formatted duration strings SHALL NOT appear in `src/a2web/`.

#### Scenario: Sub-second case

- **WHEN** `fmt_dur(420)` is called
- **THEN** the result is `"420ms"`

#### Scenario: 1.0–7.0s case

- **WHEN** `fmt_dur(1900)` is called
- **THEN** the result is `"1.9s"`

#### Scenario: 7–60s case

- **WHEN** `fmt_dur(8000)` is called
- **THEN** the result is `"8s"`

#### Scenario: Minute-plus case

- **WHEN** `fmt_dur(72_000)` is called
- **THEN** the result is `"1m12s"`

#### Scenario: Zero case

- **WHEN** `fmt_dur(0)` is called
- **THEN** the result is `"0ms"` (never `"0.0s"`)

