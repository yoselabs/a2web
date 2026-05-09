## MODIFIED Requirements

### Requirement: Tier registry with explicit ordering

The system SHALL expose `TIER_ORDER: tuple[str, ...]` and `REGISTRY: dict[str, Tier]` from `a2web.tiers.__init__`. After PR5, `TIER_ORDER` SHALL begin with `"site_handler"` followed by `"raw"`. The `"site_handler"` slot SHALL dispatch via `match_handler(url)` from `a2web.handlers`; if no handler matches, the slot SHALL emit a sentinel `TierResult` with `tier_extras["no_match"] = True` that the orchestrator interprets as "skip silently — produce no diagnostic row, fall through to the next tier."

#### Scenario: site_handler precedes raw in PR5

- **WHEN** the registry is imported in PR5
- **THEN** `TIER_ORDER == ("site_handler", "raw")` and `len(REGISTRY) >= 2`

#### Scenario: No-match handler dispatch is silent

- **WHEN** the orchestrator runs against a URL no handler matches
- **THEN** the resulting `FetchResponse.diagnostics` contains no entry with `step == "site_handler"`; the first diagnostic row is from `raw` (or whichever next tier ran)

## ADDED Requirements

### Requirement: Pre-rendered handler results bypass extraction

The orchestrator SHALL check `tier_result.tier_extras` for a `"pre_rendered"` dict. When present, the orchestrator SHALL use its `content_md`, `title`, `byline`, and `headings` directly and SHALL NOT invoke `extract_markdown`, `find_published`/`find_updated`, or `parse_metadata`. The quality gate SHALL still run on the rendered markdown; the cache write proceeds with the original `body` (typically JSON for handlers).

#### Scenario: Pre-rendered result skips trafilatura

- **WHEN** a handler returns a `TierResult` with `tier_extras["pre_rendered"] = {"content_md": "...", ...}`
- **THEN** the resulting `FetchResponse.content_md` equals the pre-rendered value and the diagnostics list contains no `extract` row

#### Scenario: Gate still runs on pre-rendered markdown

- **WHEN** the pre-rendered `content_md` is shorter than the length floor (<500 chars)
- **THEN** the gate emits `Verdict.length_floor` and the orchestrator marks the response as failed
