## Why

a2web consumes 17 shelf packages directly. **Version drift: none** — every pin is
at the newest tag. The adoption is healthy. What is not healthy is the *return
leg*: a2web has fixed bugs in shared primitives locally, and left the shared copy
broken.

### The largest un-repaid debt affects a sibling repo today

CLAUDE.md's `wire.py` entry documents three encoder defects a2web *"fixed here,
not ported"*, two of them originally filed against a2kit as **"no a2web
workaround exists"**. The shelf's `page-tsv` still ships all three:
`shelf/packages/page-tsv/src/page_tsv/render.py:96-102` loops the static
`tsv_fields` tuple with

- **no presence guard** — a pruned field is resurrected,
- **no already-a-string guard** — `:98`'s `isinstance(raw, (list, tuple)) else []`
  overwrites populated pre-encoded content with the empty marker,
- **no shape guard** — `encode_tsv` at `:99` is unwrapped, so one
  `headings`-shaped field voids the encode for the whole envelope.

a2web's fixes are at `wire.py:124-133` / `:135-153` / `:155-175`. **`a2kay`
consumes `page-tsv` today** — a sibling repo is running the bugs a2web already
diagnosed and fixed.

`page-tsv` was *deliberately* rejected for a2web adoption
(`2026-07-26-sunset-a2kit-dependency/design.md:99-104`: "Adopting re-imports the
problem"). That was the right call for a2web and the wrong outcome for the shelf:
the correct response to "this shared package is broken" is to fix it, not only to
route around it.

### Five more gaps a2web has already paid for

1. **`content-extract` has no `include_comments` / `include_tables`.** Verified:
   the shelf signature is `extract_markdown(html, url, *, include_links=False)`.
   a2web pays with two funnel exemptions whose own comment says *"This is a SHELF
   GAP, not a permanent a2web exception. The fix is to promote the knob"*, a
   direct `trafilatura>=1.12,<2` dependency, and two handlers losing links and
   headings from the same parse.
2. **`dom-schema` cannot report ROT under a universal container.**
   `handler_probe.py:136-140`'s container is `<body>`, which always matches, so a
   rotted selector reads as EMPTY rather than ROT. a2web pays with a live
   `min_candidates=5` network probe as its only rot detector — defeating the
   package's stated capability. This is the same class as the 2026-07-28 incident
   where two parsers were dead behind five green tests.
3. **`record-mine` dropped `[role=heading]`.** `detector.py:62` gates on `h1`-`h6`
   only; a2web's normative `openspec/specs/record-extraction/spec.md:15` requires
   `h1`–`h6` **or** `[role=heading]`. The shipped behaviour silently contradicts
   a2web's own spec.
4. **`any-browser` container CDP-connect failure.** zendriver's handshake fails
   in the slim container while patchright launches, so the robust rung silently
   collapses to the same engine. a2web paid with `correlated_witness` — a guard
   that makes the shelf bug *observable* rather than fixed.
5. **`json-in-html` extracts but does not normalize.** The one open EVOLVE with
   real code behind it: ~270 lines of LD/microdata/OG → uniform rows at
   `domain.py:262-292, 383-416, 501-545`.

### Adopted, then hand-rolled anyway

- **`prune_dict`** is imported at `wire.py:64` and re-exported at `:74` — and
  **called from nowhere.** Meanwhile `models.py:786` hand-writes the same
  omit-empty predicate inline, and `models.py:678` inherits `PruneEmpty` whose
  `_is_empty` is a **third** answer to the same question in the same file.
  Similarly `cli.py:134` hand-writes `model_dump(mode="json")` while
  `lean_wire.dump_model_for_wire` — documented as the *"single substrate helper
  for wire dumps"* — goes unused.
- **`fmt_dur`** is correctly elevated and used at 5 sites, all in one file.
  `llm_eval/live_sink.py:176` renders `f"{total_ms/1000:.1f}s"`, which
  **disagrees with `fmt_dur` for every value ≥ 7s**.
- **`lean-wire` is unused where its whole reason applies.**
  `llm_eval/report.py:135-136` writes `results.tsv` with stdlib
  `csv.DictWriter(delimiter="\t")` — precisely the QUOTE_MINIMAL
  raw-`\n`-inside-a-field behaviour that `pyproject.toml:50-56` cites as the
  reason lean-wire replaced a2kit's codec.
- **`http_fetch` is bypassed by jina.** `tiers/jina.py:18,133-155` builds its own
  `httpx.AsyncClient` — no impersonation, no conditional GET, hand-mapped
  verdicts, and therefore **no circuit breaker and no `FetchVerdict` closed
  enum**. (`zyte`/`firecrawl` are POSTs and `http_fetch` is GET-only — a
  legitimate gap. But `handlers/README.md:17` bans hand-rolled clients and the
  ban is scoped to `handlers/` only; `tiers/` does it freely.)
- **`a2effect` is adopted at one boundary with its taxonomy unused.** `AppError`
  appears in exactly one file. a2web raises **no** `AppError` subclass, so
  `guard_tool`'s `except AppError` branch (`error_wire.py:97`) is dead in
  production: every escaping exception takes `except Exception` and is quarantined
  into `UnexpectedDefect`, kind `"bug"`. **A missing LLM key and a genuine
  null-deref render identically.** Four of five `_KIND_LABELS` entries are
  unreachable. Four further `a2effect` surfaces sit unused while a2web hand-rolls
  them — `raises_as` (hand-written at `github.py:191-209`'s 9 branches, plus
  jina/zyte/firecrawl), `pydantic_validation_error_enricher`
  (`fetcher_response.py:85-100` re-derives the offending field by hand),
  `register_error_kind`, and `a2effect.lint` — the last in a repo that records
  losing `a2kit lint rego` as *"a real loss"*.

## What Changes

- **Promote the three encoder fixes to `page-tsv`.** Presence guard,
  already-a-string guard, shape guard — a2web's implementations are the reference.
  Then re-evaluate whether a2web's `wire.py` can consume it, and notify `a2kay`.
- **Promote the five paid-for gaps**: `include_comments`/`include_tables` to
  `content-extract` (retiring two funnel exemptions and the direct `trafilatura`
  dep), ROT-under-universal-container to `dom-schema`, `[role=heading]` to
  `record-mine`, the CDP-connect failure to `any-browser`, and the normalization
  layer to `json-in-html`.
- **Use what is already adopted.** One omit-empty predicate, not three.
  `dump_model_for_wire` in `cli.py`. `fmt_dur` in `live_sink.py`. `lean-wire` for
  `results.tsv`. `http_fetch` for jina.
- **Make the error taxonomy live.** `ResourceUnavailable`, `LLMNotAvailable`,
  `JudgeParseError` become `AppError`s with proper kinds — which immediately
  activates the four unreachable `_KIND_LABELS` and makes "missing LLM key"
  distinguishable from "bug" on the wire.
- **Scope the hand-rolled-client ban to `tiers/` as well as `handlers/`.**
- **Promote a2web's own unpromoted substrate** — `lazy.py` + `scope.py`
  (`Lazy[T]`, LIFO `ResourceScope`, `memoized`) and
  `cli.py:field_to_typer_annotation`. Both written after the 2026-07-27 sweep, so
  neither appears in its verdict table.

## Capabilities

### New Capabilities

- `substrate-adoption`: a local fix to a shared primitive SHALL be repaid
  upstream; an adopted primitive SHALL NOT be hand-rolled alongside.

### Modified Capabilities

- `record-extraction`: the shipped detector SHALL match the normative selector
  set.
- `handler-live-probe`: selector rot SHALL be distinguishable from an empty page.
- `fetch-response`: a single omit-empty predicate; the error taxonomy
  distinguishes an unavailable resource from a defect.

## Impact

- The **shelf** — `page-tsv`, `content-extract`, `dom-schema`, `record-mine`,
  `any-browser`, `json-in-html`. Each is a shelf change with its own promotion
  loop; a2web's role is to supply the reference implementation and the evidence.
- **`a2kay`** — consumes `page-tsv` today and is running the three defects.
  Notify, do not silently fix.
- `src/a2web/wire.py`, `models.py`, `cli.py` — the prune/dump duplication
- `src/a2web/tiers/jina.py` — through `http_fetch`, gaining the breaker
- `src/a2web/llm_eval/{report,live_sink}.py`
- `src/a2web/error_wire.py`, `state.py`, `packages/llm_extract/errors.py`,
  `judge.py` — the taxonomy
- `pyproject.toml` — `trafilatura` direct dep removable once `content-extract`
  has the knob
- `tests/architecture/test_trafilatura_funnel.py:47-64` — two exemptions retired

## Out of Scope

- The larger T7 structural entries — the failure-vocabulary census (10
  vocabularies, ~21 conversion sites), 30 copies of elapsed-ms, handler
  page-rendering. Real, and each is its own change.
- **Hedged-race-first-wins** (`tiers/archive.py:130-163`). DEEP, STABLE,
  substrate-indifferent — and exactly one call site. Flag-when-a-second-caller-
  appears, not now. Recorded so it is not re-proposed.
- Reddit's retry loop. Its comments encode a live-measured penalty-box model that
  `tenacity`/`stamina` would take the schedule from and lose the reason.
