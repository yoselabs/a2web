# Tasks — planner-rules-typed-priority

## 1. Introduce the rule-table primitives

- [ ] 1.1 Add `RulePriority(IntEnum)` to `src/a2web/actions/playbook.py` with members `CRITICAL = 4`, `HIGH = 3`, `MEDIUM = 2`, `LOW = 1`. Export it via `__all__`.
- [ ] 1.2 Add the internal `_RuleContext` frozen dataclass (`slots=True`, `frozen=True`) with fields `log: Sequence[Observation]`, `last: Observation | None`, `url: str`, `caps: PlannerCaps`. Kept module-private (`_`-prefixed) — it is an implementation detail.
- [ ] 1.3 Add the `PlannerRule` frozen dataclass with fields `name: str`, `priority: RulePriority`, `decide: Callable[[_RuleContext], Action | None]`. Export it via `__all__` for tests that need to inspect the rules tuple.

## 2. Port the five existing rules to PlannerRule instances

Each ported rule keeps its existing behaviour byte-for-byte (no precondition change). Priority assignments come from `design.md` Decision 1.

- [ ] 2.1 `_rule_arxiv_pdf_rewrite` → `PlannerRule(name="arxiv_pdf_rewrite", priority=CRITICAL, ...)`. URL-pattern match on `_ARXIV_PDF_RE`; emits `RewriteUrl` when `caps.url_rewrites < 1`.
- [ ] 2.2 `_rule_gate_browser_signal` → `PlannerRule(name="gate_browser_signal", priority=HIGH, ...)`. Matches when `last.kind is gate_outcome`, `last.escalation.next_tier == "browser"`, `last.verdict is not ok`, and `caps.browser_dispatches < 1`; emits `EscalateBrowser`.
- [ ] 2.3 `_rule_reddit_comment_not_found_archive` → `PlannerRule(name="reddit_comment_not_found_archive", priority=MEDIUM, ...)`. Matches the existing Reddit-comment + `not_found` rule (carrying the sibling proposal's narrowed precondition if that proposal has shipped); emits `RetryViaArchive`.
- [ ] 2.4 `_rule_cloudflare_403_429_archive` → `PlannerRule(name="cloudflare_403_429_archive", priority=LOW, ...)`. Matches `tier_outcome` + `cloudflare` + `status_code in (403, 429)`; emits `RetryViaArchive`.
- [ ] 2.5 `_rule_gate_paywall_or_block_archive` → `PlannerRule(name="gate_paywall_or_block_archive", priority=LOW, ...)`. Matches `gate_outcome` + verdict in `(paywall, block_page_detected)`; emits `RetryViaArchive`.
- [ ] 2.6 Declare the module-level tuple: `_RULES: tuple[PlannerRule, ...] = (_rule_arxiv_pdf_rewrite, _rule_gate_browser_signal, _rule_reddit_comment_not_found_archive, _rule_cloudflare_403_429_archive, _rule_gate_paywall_or_block_archive)`.

## 3. Rewrite decide_next as the enumerator

- [ ] 3.1 Replace `decide_next`'s if-chain body with: build `_RuleContext`, iterate `_RULES` sorted by `(-priority, declaration_index)`, return the first non-`None` action; fall through to `Continue()`.
- [ ] 3.2 Confirm `decide_next` signature is unchanged: `decide_next(log: Sequence[Observation], *, url: str, caps: PlannerCaps) -> Action`.
- [ ] 3.3 Add a module-level invariant assertion (or unit-tested check) that every `name` in `_RULES` is unique.
- [ ] 3.4 Confirm rule callables read only their `_RuleContext` argument — no global / settings / I/O reads. Verify by inspection (a single grep over `actions/playbook.py` for `os.`, `time.`, `random.`, `open(`).

## 4. Port and extend the test suite

- [ ] 4.1 Port every existing test in `tests/capabilities/cascade_decision_log/test_decide_next.py` unchanged — they exercise the public `decide_next` and continue to pass.
- [ ] 4.2 Rename / split existing assertions so every rule has a `test_<rule_name>_fires_when_*` and a `test_<rule_name>_does_not_fire_when_*` pair. Five rules → ten tests minimum.
- [ ] 4.3 Add `test_gate_browser_signal_outranks_reddit_archive_when_both_apply` — the regression-fix scenario from `proposal.md`: log carries a Reddit-comment + `not_found` + `js_required` tier observation AND a later gate observation with `escalation.next_tier="browser"`. Assert the planner returns `EscalateBrowser`.
- [ ] 4.4 Add `test_rule_names_are_unique` — enumerates `_RULES`, asserts every `name` field is distinct.
- [ ] 4.5 Add `test_decide_next_purity` (or extend the existing hypothesis property test) — same `(log, url, caps)` called twice returns equal actions. Already covered implicitly; make it explicit.

## 5. Validate and archive cleanup

- [ ] 5.1 Run `make check` — lint + ty + tests + coverage ≥ 85 % all pass.
- [ ] 5.2 Run `make bench` once; confirm the Reddit-JS-shell case in `eval/corpus.yaml` now escalates to browser. Record the finding in `eval/findings_<date>.md`.
- [ ] 5.3 If `tighten-archive-rule-for-reddit` has already shipped, the Reddit rule's precondition is the narrowed one from that proposal; no further change. If it has not shipped, mark it as superseded in its `proposal.md` and archive it with a one-line note when this change archives.
- [ ] 5.4 Archive this change under `openspec/changes/archive/<date>-planner-rules-typed-priority/` once shipped.
