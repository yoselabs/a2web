## ADDED Requirements

### Requirement: Archive tier hedges Wayback and archive.ph

The system SHALL define `ArchiveTier` in `src/a2web/tiers/archive.py` implementing the `Tier` protocol with `name = "archive"`. `ArchiveTier.fetch` SHALL launch two concurrent upstream lookups under `anyio.create_task_group()`:

1. **Wayback CDX** — `GET https://web.archive.org/cdx/search/cdx?url=<url>&output=json&limit=1&fl=timestamp,original`. On hit, fetch `https://web.archive.org/web/<timestamp>id_/<url>` (the `id_` modifier returns the unmodified original snapshot).
2. **archive.ph** — `GET https://archive.ph/newest/<url>` via curl_cffi (chrome120 impersonation; archive.ph is Cloudflare-fronted).

The first task to land a result with `verdict == Verdict.ok` SHALL win; the loser SHALL be cancelled. The result body SHALL have any Wayback chrome stripped before being wrapped as `tier_extras["pre_rendered"]` (extracted via trafilatura inside the tier).

#### Scenario: Wayback wins, archive.ph cancelled

- **WHEN** Wayback CDX returns a snapshot before archive.ph responds
- **THEN** the result body is the Wayback-stripped snapshot, `tier_extras["source"] == "wayback"`, and the archive.ph task is cancelled (no curl_cffi connection leak)

#### Scenario: archive.ph wins

- **WHEN** archive.ph responds first with a 200
- **THEN** `tier_extras["source"] == "archive.ph"` and the Wayback task is cancelled

#### Scenario: Both miss

- **WHEN** Wayback CDX returns no rows AND archive.ph returns 404
- **THEN** the tier returns `verdict == Verdict.not_found` with `tier_extras["pre_rendered"]` absent

### Requirement: Archive results carry source + age metadata

The tier SHALL set `tier_extras["from_archive"] = True` on every successful result and (when source is Wayback) `tier_extras["snapshot_age_days"]` as the integer days between the snapshot timestamp and now.

#### Scenario: Wayback hit exposes snapshot age

- **WHEN** the Wayback snapshot timestamp is `20240101000000`
- **THEN** `tier_extras["snapshot_age_days"]` is the integer day delta from now

#### Scenario: from_archive flag prevents cache write

- **WHEN** the orchestrator processes an archive-sourced result
- **THEN** the cache write is skipped (no row in the `cache` table for the URL+profile_hash key)

### Requirement: Archive tier is in REGISTRY but not in TIER_ORDER

The system SHALL register `ArchiveTier` in `REGISTRY` under key `"archive"` but SHALL NOT include `"archive"` in `TIER_ORDER`. Default fetches SHALL never invoke the archive tier; it is dispatched out-of-band by the orchestrator only when the playbook returns `RetryViaArchive`.

#### Scenario: TIER_ORDER excludes archive

- **WHEN** the registry is imported in PR7b
- **THEN** `"archive" in REGISTRY` and `"archive" not in TIER_ORDER`
