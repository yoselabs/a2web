## 1. Template + boundary type

- [ ] 1.1 In `src/a2web/packages/llm_extract/prompts.py`, add a frozen `PromptParts` dataclass with three string fields: `system`, `cache_prefix`, `tail`. All `slots=True`.
- [ ] 1.2 Add a `PromptTemplate.render(content: str, ask: str) -> PromptParts` method. Existing templates (`WEBFETCH_DEFAULT_V1`, `TERSE_V1`, `JUDGE_V1`) keep returning the degenerate shape `PromptParts(system="", cache_prefix="", tail=<formatted user_template>)` — full message in `tail`, nothing cacheable. Backwards-compatible.
- [ ] 1.3 Add a new module-level constant `EXTRACT_CACHEABLE_V1` whose render produces: `system` carries the rules block (125-char quotes, copyright, lyrics, response-mode instruction); `cache_prefix` carries the page content with framing; `tail` is `"\nQuestion: {ask}\n"`. Body lengths chosen so a typical page lands ≥1024 tokens in the cache_prefix (OpenAI auto-cache floor).
- [ ] 1.4 Export `EXTRACT_CACHEABLE_V1` + `PromptParts` from `prompts.__all__`.

## 2. Provider Protocol widening

- [ ] 2.1 In `providers/base.py`, extend `Provider.complete()` signature with optional `parts: PromptParts | None = None`. When `parts` is provided, providers SHALL use the cache-aware path; when `None`, providers SHALL use the legacy `system + user` flat-string path (so judge + WebFetchBaseline calls keep working unchanged).
- [ ] 2.2 Update `ProviderResponse` if needed (it already carries cache_creation/cache_read via `extract_token_counts` — confirm and leave unchanged).

## 3. AnthropicProvider — explicit markers

- [ ] 3.1 In `providers/anthropic.py`, when `parts` is provided: send `system` as `[{"type":"text","text":parts.system,"cache_control":{"type":"ephemeral"}}]` if non-empty, else omit. Send user content as a list of TWO blocks: `[{"type":"text","text":parts.cache_prefix,"cache_control":{"type":"ephemeral"}}, {"type":"text","text":parts.tail}]`.
- [ ] 3.2 When `parts is None`: keep the existing flat-string path. Single-block user content. No markers. Behavior unchanged.
- [ ] 3.3 Verify the existing `_price_for` + `extract_token_counts` math still produces correct numbers under the dual-block path (it should — Anthropic returns usage at the message level, not per block).

## 4. ClaudeCodeProvider — no markers, stability only

- [ ] 4.1 In `providers/claude_code.py`, when `parts` is provided: set `system_prompt=parts.system` and pass `prompt=parts.cache_prefix + parts.tail` (concatenation, byte-identical to the legacy single-string).
- [ ] 4.2 Add a one-line module docstring note recording the probe finding ("`claude-agent-sdk` exposes no `cache_control` API; the CLI binary handles caching given byte-stable prefix discipline").
- [ ] 4.3 No new code paths beyond the parts → strings unpack. Behavior remains "send strings; trust the CLI."

## 5. Extractor wiring

- [ ] 5.1 In `extractor.py::Extractor.extract()`, replace the current `user = self._template.user_template.format(...)` with `parts = self._template.render(truncated, ask)` followed by `await self._provider.complete(parts=parts, ...)`.
- [ ] 5.2 The next-links suffix path SHALL append to `parts.tail`, NOT to `cache_prefix` (the suffix only fires conditionally — would defeat caching).
- [ ] 5.3 No change to the sqlite ExtractionCache (layer-2) path. It continues to hash `(truncated_content, ask)` and short-circuit before the provider call.

## 6. Default template selection

- [ ] 6.1 In `src/a2web/llm_resource.py`, the production `Extractor` SHALL be constructed with `template=EXTRACT_CACHEABLE_V1`.
- [ ] 6.2 The `WebFetchBaseline` eval system in `src/a2web/llm_eval/` SHALL continue to use `WEBFETCH_DEFAULT_V1` — verify and leave unchanged.
- [ ] 6.3 The `Judge` continues to use `JUDGE_V1` unchanged.

## 7. Prefix byte-stability snapshot test

- [ ] 7.1 Add `tests/packages/test_prompt_cache_stability.py` with a single test:
  - Build `parts1 = EXTRACT_CACHEABLE_V1.render(content=<fixed page>, ask="What is X?")`
  - Build `parts2 = EXTRACT_CACHEABLE_V1.render(content=<fixed page>, ask="Who wrote this?")`
  - Build `parts3 = EXTRACT_CACHEABLE_V1.render(content=<fixed page>, ask="A wordy, long-form question that varies substantially in tokenization shape.")`
  - Assert `parts1.system == parts2.system == parts3.system`
  - Assert `parts1.cache_prefix == parts2.cache_prefix == parts3.cache_prefix`
  - Assert the three tails differ pairwise.
  - Assert `parts1.cache_prefix` contains the page content verbatim (smoke).
- [ ] 7.2 Add a second test that asserts the *degenerate* render path (e.g. `WEBFETCH_DEFAULT_V1.render(...)`) produces `cache_prefix == ""` and a non-empty `tail`. Guards the backwards-compat invariant.

## 8. Existing test pass + lint

- [ ] 8.1 Run `make test` (subset that touches `llm_extract`): all green.
- [ ] 8.2 Run `make lint` + `make ty`: zero warnings.
- [ ] 8.3 Run `make check`: full gate green (coverage ≥85%).

## 9. Changelog + version

- [ ] 9.1 Bump `pyproject.toml` to v0.19.0.
- [ ] 9.2 Add v0.19.0 entry to `CHANGELOG.md`. Note: new template, two-block Anthropic message, no agent-visible behavior change, cost reduction on multi-Q sessions, byte-stability snapshot test.
- [ ] 9.3 Update `BACKLOG.md`: mark this item complete; add follow-up "measure cache hit rate in production telemetry" under Phase D.

## 10. Archive

- [ ] 10.1 `make install-global` so Claude Code's MCP entry picks up the new binary.
- [ ] 10.2 Move `openspec/changes/make-llm-prompts-cache-compliant/` to `openspec/changes/archive/2026-05-23-make-llm-prompts-cache-compliant/`.
