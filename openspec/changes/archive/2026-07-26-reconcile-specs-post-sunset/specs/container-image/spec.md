## MODIFIED Requirements

### Requirement: Configuration and secrets come from the environment at runtime

The image SHALL read all configuration from the environment it already supports (`A2WEB_*` and provider/secret env such as `ANTHROPIC_API_KEY` / `A2WEB_LLM_*` / `A2WEB_ZYTE_KEY` / `GOOGLE_*`). Secrets SHALL NOT be baked into any image layer. The sqlite cache SHALL live at a path that can be backed by a mounted volume so it survives container restarts.

#### Scenario: Env-supplied secret reaches settings

- **WHEN** the container is started with `A2WEB_ZYTE_KEY` (or another supported var) set in its environment
- **THEN** `AppSettings` resolves it, with no key present in any built image layer

#### Scenario: Cache persists across restarts on a mounted volume

- **WHEN** the sqlite cache path is backed by a mounted volume and the container is restarted
- **THEN** the previously written cache is still present
