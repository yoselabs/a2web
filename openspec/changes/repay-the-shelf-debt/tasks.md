# Tasks

Six shelf changes plus the local repairs. This will not land in one sitting —
sequence by blast radius (design D3) and close items individually.

Resolve the shelf loop lazily at the first adopt/promote checkpoint, per
CLAUDE.md: find the clone, read `<shelf>/docs/agent-loop.md`, `git pull` there.
Never commit a local `path=`/editable shelf source.

## 1. `page-tsv` — DONE 2026-08-01 (shelf `page-tsv-v0.2.0`, `lean-wire-v0.2.0`)

**The section title was wrong and is corrected below (1.4).** This was not "the
only debt with a live cross-repo consumer" — it had no live consumer at all.

- [x] 1.1 Promote the **presence guard** — a pruned field stays pruned.
- [x] 1.2 Promote the **already-a-string guard** — pre-encoded content survives.
- [x] 1.3 Promote the **shape guard** — one untabulatable field no longer voids
      the whole envelope's encode.
- [x] 1.3b **A FOURTH defect, not in the original list:** the header came from
      `rows[0]`, deleting every key that row happened to lack. Found in a2web
      2026-07-31, still live in `page-tsv` in two places. Fixed — and it turned
      out to be the interesting one, see 1.6.
- [x] 1.4 ~~Notify `a2kay` before release.~~ **The claim was false; verified.**
      a2kay imports `page_tsv.Page` as a TYPE in three routers and nothing
      else. Its CLI renders compact JSON explicitly and its own docstring says
      *"Token-lean `page-tsv`/TSV type-routing is a later enhancement"* — no
      a2kay code path reaches the encoder, so nothing shipped wrong and there is
      no output change to notify anyone about. What was true: a2kay is *primed*
      to turn it on, and these four are exactly what would have bitten then.
      Recorded in shelf ledger 0075 rather than quietly dropped.
- [x] 1.5 Correct the rejection note in
      `openspec/changes/archive/2026-07-26-sunset-a2kit-dependency/design.md`.
      Both rejections stand; the correction is that *"a2web routed around it"*
      was never the same as *"it is fixed"*, and the document read as if it were.
- [x] 1.6 Re-evaluate whether a2web's `wire.py` can consume `page-tsv`.
      **Answer: no, re-affirmed on the original grounds** (design Open
      Questions) — page-tsv's centre of gravity is the `EncodingPlan` inference
      that `_TSV_FIELDS` exists to refuse, and it exports no `encode_rows`
      equivalent. **But the fourth defect transferred something better:** three
      callers had answered `encode_tsv`'s "what are the columns?" and all three
      answered `rows[0]`. Rule of three on a *defect*. The rule moved down to
      `lean_wire.derive_columns` (v0.2.0); a2web adopted it and deleted its copy,
      so it shares the mechanism without the inference spine.
- [x] 1.7 **Unplanned, found en route: the shelf's own gate was not running 8 of
      26 package suites** — 174 tests, `a2effect` and `page-tsv` among them.
      Surfaced only because six new `lean-wire` tests did not move the root
      collection count. `testpaths` is hand-maintained and pytest is silent
      about an absent package. Fixed and guarded in both directions
      (`tests/test_gate_covers_every_package.py`); the shelf gate went 472 → 649
      tests and its coverage base 2610 → 3544 statements. Shelf ledger 0077.
      Same shape as a2web's `tach.toml` finding — worth watching for a third.

## 2. `record-mine` — the shipped detector contradicts a2web's own spec

- [ ] 2.1 Promote `[role=heading]` to `detector.py:62`, which gates on `h1`-`h6`
      only. `openspec/specs/record-extraction/spec.md:15` requires either.
- [ ] 2.2 Add a captured fixture: a listing whose item titles carry
      `role="heading"`, asserting detection.
- [ ] 2.3 Add the test asserting the delegated selector set matches the normative
      one, so the two cannot diverge again silently.

## 3. `content-extract` — retire two funnel exemptions

- [ ] 3.1 Promote `include_comments` and `include_tables`. The shelf signature is
      `extract_markdown(html, url, *, include_links=False)`.
- [ ] 3.2 Retire the two exemptions in
      `tests/architecture/test_trafilatura_funnel.py:47-64`, whose own comment
      says *"This is a SHELF GAP, not a permanent a2web exception."* **Not
      before** the knobs ship — the exemptions are honest today.
- [ ] 3.3 Remove the direct `trafilatura>=1.12,<2` dep (`pyproject.toml:143`).
- [ ] 3.4 Confirm the two comment-thread handlers regain links and headings from
      the same parse.

## 4. `dom-schema` — rot vs empty

- [ ] 4.1 Promote ROT reporting under a universal container.
      `handler_probe.py:136-140` uses `<body>`, which always matches, so a rotted
      selector reads as EMPTY.
- [ ] 4.2 Make rot detectable offline against captured markup — today the live
      `min_candidates=5` network probe is the only detector.
- [ ] 4.3 Consider widening `dom-schema` adoption past 2 of 9 handlers.
      `handlers/_reddit_html.py:28,126` hand-rolls 294 lines of
      `selectolax.parser.HTMLParser` + CSS traversal with **no ROT verdict** —
      note this interacts with `close-guards-that-read-green` §1, which replaces
      two reddit regexes.

## 5. `json-in-html` and `any-browser`

- [ ] 5.1 Promote the normalization layer — ~270 lines of LD/microdata/OG →
      uniform rows at `domain.py:262-292, 383-416, 501-545`. **Sequence after
      `lift-the-item-set-and-renderer`** has moved the renderer.
- [ ] 5.2 File the `any-browser` container CDP-connect failure: zendriver's
      handshake fails in the slim container while patchright launches, so the
      robust rung silently collapses to the same engine. `correlated_witness`
      makes it observable; it is not fixed.

## 6. Use what is already adopted

- [ ] 6.1 One omit-empty predicate. Today: `models.py:786` inline,
      `models.py:678` via inherited `PruneEmpty`, and `prune_dict` imported at
      `wire.py:64`, re-exported at `:74`, **called nowhere**.
- [ ] 6.2 `cli.py:134` — use `lean_wire.dump_model_for_wire`, documented as the
      *"single substrate helper for wire dumps"*.
- [ ] 6.3 `llm_eval/live_sink.py:176` — use `fmt_dur`. It currently renders
      `f"{total_ms/1000:.1f}s"`, which disagrees for every value ≥ 7s.
- [ ] 6.4 `llm_eval/report.py:135-136` — write `results.tsv` through `lean-wire`,
      not `csv.DictWriter(delimiter="\t")`. That is exactly the QUOTE_MINIMAL
      behaviour `pyproject.toml:50-56` cites as lean-wire's reason to exist.

## 7. jina through `http_fetch`

- [ ] 7.1 Route `tiers/jina.py:18, 133-155` through `http_fetch` — it gains
      impersonation, conditional GET, the circuit breaker, and the `FetchVerdict`
      closed enum, none of which it has today.
- [ ] 7.2 Decide the `zyte`/`firecrawl` question: widen `http_fetch` to POST, or
      record them as an explicit exception (design Open Questions). They POST to
      JSON APIs; `http_fetch` is GET-only.
- [ ] 7.3 Extend `handlers/README.md:17`'s hand-rolled-`httpx.AsyncClient` ban to
      `tiers/`, which is where it is being violated.

## 8. Make the error taxonomy live

- [ ] 8.1 Make `ResourceUnavailable` (`state.py:186`), `LLMNotAvailable`
      (`packages/llm_extract/errors.py:6`) and `JudgeParseError` (`judge.py:63`)
      `AppError`s with proper kinds.
- [ ] 8.2 Confirm `guard_tool`'s `except AppError` (`error_wire.py:97`) is now
      reachable, and that the four unreachable `_KIND_LABELS` entries
      (`:48-54`) are produced.
- [ ] 8.3 Verify a missing LLM key no longer renders as
      `"Internal error (UnexpectedDefect): …"`.
- [ ] 8.4 Coordinate with `close-wire-level-adr-0009-leaks`, which covers the
      same dead branch from the wire-leak side: this change makes it reachable,
      that one asserts what reaches it.
- [ ] 8.5 Evaluate `a2effect.translate.raises_as` against the hand-written
      equivalents — `handlers/github.py:191-209` (9 branches),
      `tiers/jina.py:139-161`, `zyte.py:106-109`, `firecrawl.py:62-65`.
- [ ] 8.6 Evaluate `a2effect.enrichers.pydantic_validation_error_enricher`
      against `fetcher_response.py:85-100`, which re-derives the offending field
      by hand with an `"unknown"` fallback.
- [ ] 8.7 Read `a2effect.lint` before actioning the Rego re-homing backlog entry
      — it is a declared-error-closure checker and may or may not be the
      replacement.

## 9. Promote a2web's own unpromoted substrate

- [ ] 9.1 Assess `lazy.py` (43) + `scope.py` (109) against DEEP · STABLE · WINS.
      Both were written after the 2026-07-27 sweep, so their absence from its
      verdict table is an oversight, not a judgement.
- [ ] 9.2 **Do not loosen the cold-start guarantee.** `scope.py` is load-bearing
      for `test_cold_start_laziness.py`; if the shelf version needs a more general
      contract, keep it local.
- [ ] 9.3 Assess `cli.py:field_to_typer_annotation` (MCP tool → Typer CLI
      derivation).

## 10. Close out

- [ ] 10.1 `make check` green.
- [ ] 10.2 Record which of the six shelf items landed and which are open — this
      change is a ledger, and a partially-repaid ledger must say so.
- [ ] 10.3 Move the closed T7 entries to `BACKLOG-CLOSED.md`. Leave the large
      structural ones (failure-vocabulary census, elapsed-ms, handler
      page-rendering) open — they are out of scope here.
- [ ] 10.4 Re-record the two deliberate non-promotions so they are not
      re-proposed: hedged-race-first-wins (one call site) and reddit's retry loop
      (its comments encode a live-measured penalty-box model a library would take
      the schedule from and lose the reason).
