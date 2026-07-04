## ADDED Requirements

### Requirement: Reddit handler prefers RSS over walled .json
The Reddit handler SHALL use the RSS projection (see `reddit-rss-access`) as its primary fetch path for `search`/`listing`/`thread` shapes, because the anonymous `.json` endpoint is Datadome-walled. The handler SHALL emit the eager critical browser hint (see `retrieval-completeness`) when RSS is exhausted rather than returning a silent low-signal failure.

#### Scenario: Reddit search uses RSS not .json
- **WHEN** a Reddit search URL is handled
- **THEN** the handler fetches via `.rss`, and if that is exhausted emits the eager critical hint

#### Scenario: Reddit handler never silently drops
- **WHEN** every Reddit path is walled
- **THEN** the handler returns `status: failed` + `retrieval_incomplete` + the critical hint, never a silent empty result
