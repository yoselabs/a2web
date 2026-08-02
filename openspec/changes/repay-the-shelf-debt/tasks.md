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

## 3. `content-extract` — DONE 2026-08-02 (shelf `content-extract-v0.3.0`, `convert-md-v0.9.0`)

- [x] 3.1 Promoted both knobs, as a two-package chain: `convert_md.convert_html`
      gained them (they are trafilatura's own, previously hardcoded at
      `include_tables=True, include_comments=False`) and
      `content_extract.extract_markdown` plumbs them through `_extract_sync`.
      Defaults unchanged in both — strictly additive. Verified by reversion at
      BOTH layers, because "accepted but not plumbed" is the exact defect shape:
      hardcoding back in `convert_md` fails 2 tests, dropping them from the
      `partial(...)` in the async door fails 2 more.
- [x] 3.2 Retired — `_FUNNEL_EXEMPT` is now `frozenset()`. The docstring records
      what it held and why, because an exemption written WITH its reason is what
      made this closable rather than permanent. Guard re-verified non-vacuous by
      reintroducing a direct `trafilatura.extract` in `reddit.py` and watching it
      fail.
- [x] 3.3 Removed. No `trafilatura` reference survives in `src/` outside
      comments and the `ContentCandidate.source` string label.
- [x] 3.4 **Confirmed, and the answer is half no — measured, not assumed.**
      Against the captured `oldreddit_thread.html`:
      **links: yes, 6** from the same parse where the old path extracted none.
      **headings: nothing to regain — the page has ZERO `h1`-`h6`.** old.reddit
      renders the thread without them, so the synthesized
      `Heading(level=1, text=title)` remains the only heading available and
      switching to `extracted.headings` would have emptied the list. The links
      are available but not yet plumbed: `tiers.Rendered` has no `links` field,
      which is a wider change than this section. Recorded in `BACKLOG.md`.
      Also verified NO metadata regression: `content_extract` calls the same
      `trafilatura.extract_metadata` internally and returns byte-identical
      title/byline on that fixture. The knob itself is live on the real shape —
      `include_comments=True` yields 354 chars vs 225 by default.
      **Bonus, unplanned:** each handler had been parsing the document TWICE (an
      `extract` plus a separate `extract_metadata`); the funnel returns both from
      one parse, so routing them deleted the second call.

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

## 6. Use what is already adopted — DONE 2026-08-02

- [x] 6.1 One predicate. `_prune_wire` could not use `prune_dict` (it regroups
      debug keys and scopes an omit-when-False to `retrieval_incomplete`), so it
      needed the PREDICATE — promoted public as `lean_wire.is_empty`
      (lean-wire v0.3.0) rather than copied a fourth time. The dead
      `prune_dict` re-export in `wire.py` is deleted: **zero callers in `src/`
      OR `tests/`**. Note the old inline test AGREED with the shelf's on a2web's
      types — that is the finding, not a reprieve: nothing compared them, and
      they were never the same test (`value == []` is equality against a
      literal, `is_empty` is isinstance-plus-length; they diverge on any custom
      `__eq__`).
- [x] 6.2 `cli.py` uses `dump_model_for_wire`. CLI contract gate byte-identical
      (17 passed) — which is the point: it produces the same bytes TODAY, so
      nothing would have failed on the day the shelf's wire-dump seam changed
      and a2web's private `model_dump` did not.
- [x] 6.3 `live_sink.py` uses `fmt_dur`. **The task understated the divergence:**
      they disagree BELOW one second too (`800ms` vs `0.8s`), not only at ≥7s
      where `fmt_dur` drops the decimal (`12s` vs `12.4s`) and switches to
      `1m01s` past a minute against `61.0s`. Verified by running both over eight
      magnitudes.
- [x] 6.4 `results.tsv` goes through `lean_wire.encode_tsv`. **This was a live
      hazard, not a tidiness item.** Four columns are LLM-authored prose
      (`quality_reason`, `clarity_reason`, `next_links_reason`, `fetch_error`);
      `csv.DictWriter(delimiter="\t")`'s QUOTE_MINIMAL emits a newline-bearing
      cell QUOTED with the newline still literal inside, so one logical row
      spans several physical lines and every `awk`/`cut` pipeline over the file
      misparses silently. `columns=` is passed, not derived — `_RESULTS_FIELDS`
      is a declared contract and a column must survive a run where every row
      elides it. Pinned by
      `test_results_tsv_stays_one_row_per_line.py`; reversion-verified (the old
      writer fails 2 of the 3).

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

- [x] 8.1 **Two of three, and the third is DECLINED with a reason.**
      `ResourceUnavailable` is `InfrastructureError` and `LLMNotAvailable` is
      `AuthError` (both landed 2026-07-31). `JudgeParseError` stays a plain
      `ValueError`: `Judge` is imported ONLY under `llm_eval/` (verified — zero
      references in `routers.py` / `fetcher.py` / `llm_resource.py`), it is
      raised by the bench judge and caught at three sites in `runner.py`, and it
      never crosses the tool boundary. Typing it would make the taxonomy claim
      something false — an `AppError` subclass advertises "this can reach the
      wire typed", and this one structurally cannot.
- [x] 8.2 Confirmed by execution through the real MCP transport, not by reading:
      a `LLMNotAvailable` escaping a tool renders as
      `Authentication required (LLMNotAvailable): …` with
      `kind: auth`, `retryable: false` on the structured channel, and a
      `ResourceUnavailable` as `Service unavailable (…)` with `kind: infra`,
      `retryable: true`. The branch was reachable and unpinned — now pinned by
      three tests in `test_error_envelope_wire.py`, reversion-verified by
      de-typing `LLMNotAvailable` back to a bare `RuntimeError`.
- [x] 8.3 Verified: no `Internal error` / `UnexpectedDefect` in the prose for a
      missing key. The third test is the ANTI-VACUITY pair — a `ZeroDivisionError`
      must still quarantine to `Internal error (UnexpectedDefect)`, so a
      `format_error_prose` that degraded to labelling everything by class name
      cannot pass the first two.
- [x] 8.4 `close-wire-level-adr-0009-leaks` shipped 2026-07-31; the tests added
      here are the "assert what reaches it" half it left open.
- [x] 8.5 **Evaluated. DECLINED — the shapes do not match, and adopting it
      would break the tier contract.** `raises_as` maps a foreign exception to a
      typed `AppError` and RE-RAISES it. All four named sites do the opposite:
      they CATCH and RETURN a `TierResult` carrying a non-ok `Verdict`. That is
      not a stylistic difference. A non-ok tier verdict is a normal ladder
      outcome — `fetcher._AfterTier.CONTINUE` ("advance to the next tier") — so a
      jina timeout must let the ladder try the next rung. Routing those four
      sites through `raises_as` would turn every recoverable tier failure into an
      exception escaping the tier, i.e. a fetch that stops at the first
      hiccup instead of escalating. The taxonomy is for errors that REACH THE
      CALLER; a tier verdict is a routing input that never does.
      Two things found while probing, both recorded rather than acted on:
      (a) `gidgethub.RateLimitExceeded` and `InvalidField` are both subclasses of
      `BadRequest`, so `github.py`'s except-ORDER is load-bearing. `raises_as`
      iterates its mapping dict in insertion order, so it would preserve that —
      but silently, where the `except` chain at least makes the ordering visible
      as code. A future reordering of that dict is a live hazard the current
      form does not have.
      (b) The one place the taxonomy DOES belong on this path is already done:
      `LLMNotAvailable` (§8.1), which genuinely reaches the tool boundary.
- [x] 8.6 **Evaluated. Adopted for field extraction, not for translation** — and
      the evaluation surfaced a real defect underneath. The enricher's RAISING
      shape does not fit (`_project_routing` logs `tolerance="skip"` and returns
      `None`; the caller still gets `answer`), but its FIELD EXTRACTION does, so
      `_validation_error_fields` now calls it and reads `details["fields"]`.
      What the hand-rolled version got wrong, both now fixed and pinned:
      it read `errors()[0]` only, so a payload violating TWO closed enums at once
      logged one and the second was invisible (the operator fixes the named enum,
      re-runs, and the same event fires naming a field that was wrong all along);
      and its `"unknown"` fallback fired for a REAL `ValidationError` whose first
      error had an empty `loc`, making a diagnosable event indistinguishable from
      an undiagnosable one. Added `violating_fields` (all of them) alongside
      `field` (the first — an existing operator grep keeps working). `"unknown"`
      now means exactly one thing: not a `ValidationError` at all.
      **The event was previously untested in full** — not that it fires, not what
      it names, not that `answer` survives. `tests/capabilities/wobble_funnel/
      test_routing_mirror_wobble_event.py` closes that, with an anti-vacuity
      floor (a valid boundary projects and emits nothing) and a reversion check
      (capping extraction at the first field fails the two-violation test).
      The test captures off the `a2web` logger directly rather than via `caplog`:
      the logger sets `propagate=False`, so a caplog version passed alone and
      failed in the full suite — capturing by accident, whose mirror image is
      asserting nothing by accident.
- [x] 8.7 **Read, run, and probed. It is NOT the Rego replacement.** Three real
      rules exist and are registered (`A2K-RAISES-CLOSURE`,
      `A2K-RAISES-NOT-TYPED`, `A2K-RAISES-UNCOVERED`), but they key on an
      `Annotated[T, Raises(...)]` return-annotation convention a2web does not
      use anywhere. **`lint_path(Path("src/a2web"))` reports 0 messages over the
      whole tree — which reads as "clean" and means "not applicable".** That is
      the exact guard-reads-green shape this repo keeps finding, so it is
      recorded rather than cited as a pass.
      Narrower still, verified by probe: `A2K-RAISES-NOT-TYPED` only flags a
      `Raises(...)` member whose dotted prefix is in a hardcoded six-library
      allowlist (`httpx`, `asyncpg`, `redis`, `sqlalchemy`, `fastapi`,
      `starlette`). A probe file raising `httpx.HTTPError` fires; the identical
      one raising `curl_cffi.CurlError` does not — and a2web's tiers use
      `curl_cffi`, not `httpx`. So even after adopting the annotation
      convention, it would say nothing about a2web's actual dependencies.
      Rego was a general policy engine over arbitrary rules; this is three rules
      over one convention. Recorded in `BACKLOG.md` against the re-homing entry.

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
