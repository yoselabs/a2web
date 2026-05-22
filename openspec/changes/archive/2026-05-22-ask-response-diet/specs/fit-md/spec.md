## REMOVED Requirements

### Requirement: Pruning filter produces a denser markdown

**Reason**: The `prune_html` pruning filter was never shipped; `fit_md` has been unconditionally `None` since v0.3. JSON-synth (v0.11) and the LLM extractor superseded the "denser markdown" goal. The capability is dead code reservation.

**Migration**: None. No caller ever received a non-`None` `fit_md`. Callers wanting a denser representation use `ask` (server-side extraction) instead of reading `fit_md`.

### Requirement: fit_md populated only on successful fetches

**Reason**: `fit_md` and `TokenCounts.fit` are deleted from the model. `fit_md` is removed from `FetchResponse`; `TokenCounts` no longer carries a `fit` field. There is no field left to conditionally populate.

**Migration**: Consumers reading `FetchResponse.fit_md` must remove the access — the field never carried data (always `None`). Consumers reading `FetchResponse.tokens.fit` must remove the access; `tokens.full` (a character count) remains on `FetchResponse` under `debug`.

### Requirement: Pre-rendered handler results skip pruning

**Reason**: The rule (`fit_md = content_md` for handler-rendered pages, skip `prune_html`) only existed to populate `fit_md`. With `fit_md` deleted there is nothing to set and no `prune_html` to skip.

**Migration**: None. Handler-rendered markdown continues to flow through `content_md` unchanged.
