# Tasks

## 1. Audit before guarding (D4)

- [ ] 1.1 Per handler, record whether its success is defined by a parse yielding
      units, and whether it can distinguish "parsed nothing" from "parsed a
      genuinely empty page". A grep found no zero-parse guard in seven of nine;
      that is a hint, not the answer. Write the table into the change.
- [ ] 1.2 Per handler, record which `re.compile` sites run over MARKUP (in
      scope for conversion, later) versus over URLs / JSON / free text (out of
      scope, regex is right there). TEN files call `re.compile` (`grep -l`,
      verified); the markup/non-markup split is not visible in that count and is
      the number that actually scopes the follow-up.
- [ ] 1.3 Name any handler where the guard MUST NOT be applied, with the reason.
      A handler that returns non-`ok` on a real empty listing sends the cascade
      to a browser for nothing.

## 2. Prove the defect before fixing it

- [ ] 2.1 Capture a real arXiv listing page to `tests/fixtures/`. Record the
      capture date and count the `dt`/`dd` pairs in the COMMITTED file by
      inspection — that count is the guard's non-vacuity floor. Do NOT use the
      page's self-described count: there is no single one (per-section
      `showing N of M`, a `showing first N of M` partial marker, `Total of 408
      entries`), and the page renders a variable number of day-sections between
      requests. Prefer capturing a multi-section render, since single-section is
      the easier case and would not exercise the pairing across a section break.
- [ ] 2.2 Failing test: the arXiv listing handler yields entries commensurate
      with the capture's own `dt`/`dd` pair count (2.1). MUST fail today, at
      zero.
- [ ] 2.3 Failing test: a listing parse yielding zero entries does not return
      `Verdict.ok`. MUST fail today.
- [ ] 2.4 Note in the commit which EXISTING test stayed green throughout
      (`test_arxiv_listing_html_parser_extracts_entries`) and why — the
      hand-written fixture is the oracle-endogeneity instance the design is
      built on, and it is worth naming once, precisely.

## 3. The verdict guard (D1 — first, because it is the defect)

- [ ] 3.0 **DECIDE FIRST, it is not settled:** which verdict a zero-yield parse
      returns. The design says "non-`ok`" and stops there, but `empty_result(url,
      verdict)` needs a concrete member and the closed set constrains the choice:
      `blank_page` asserts the page was blank (an observation the handler did not
      make), `not_found` asserts absence, `length_floor` is what happens today by
      accident and is about rendered size rather than parse yield, `other` is
      honest but carries no signal. Pick one, write the reason into the helper's
      docstring, and check how `classify_terminal` treats it — a verdict that
      routes to a `critical` hint would over-warn on a genuinely empty listing.
- [ ] 3.1 `handlers/_common.py` gains the zero-yield helper, beside
      `empty_result` / `map_non_ok`. Not inline in the handler — the audit may
      find siblings, and a second inline copy is how the four-way install
      duplication happened one change ago.
- [ ] 3.2 `arxiv.py::_fetch_listing` consults its parse yield before choosing a
      verdict.
- [ ] 3.3 Apply to whichever handlers task 1.1 identified, and to none it
      excluded.
- [ ] 3.4 Confirm 2.3 passes.

## 4. The parser (D2 — second, because it is the instance)

- [ ] 4.1 Replace `_LIST_ABS_RE` / `_LIST_TITLE_RE` / `_LIST_AUTHORS_RE` and
      `_parse_listing_entries` with a selectolax walk: `dl#articles` →
      `zip(dt, dd)` → `a[title='Abstract']` href, `div.list-title`,
      `div.list-authors`. Delete the regexes; do not leave them as a fallback —
      a fallback that fires on a real page hides the failure the guard exists to
      surface.
- [ ] 4.2 Verify against a MULTI-SECTION render specifically: `zip(dt, dd)`
      must stay aligned across an `<h3>` section break, and entries from every
      section must be parsed. A single-section render passes trivially and is
      what was observed first.
- [ ] 4.3 Repoint `test_arxiv_listing_html_parser_extracts_entries` at the
      capture. Do not leave a hand-written fixture standing as the ORACLE for
      whether the parser matches arXiv. KEEP a synthetic fixture where one is
      controlling an entry count to exercise the 10-candidate cap — that is a
      different job and deleting it would lose cap coverage.
- [ ] 4.4 Confirm 2.2 passes.

## 5. Gate

- [ ] 5.1 `make check` green, coverage ≥85%.
- [ ] 5.2 `make arch` green; `uv run tach check` clean.
- [ ] 5.3 Every new guard watched failing (task 2) and carrying a non-vacuity
      floor.
- [ ] 5.4 Name any existing test that asserted the old behaviour and had to
      change. `test_arxiv_listing_candidates_shape` and the happy-path test both
      touch this parser.

## 6. Evidence

- [ ] 6.1 Live probe: `ArxivHandler.fetch("https://arxiv.org/list/cs.CL/recent")`
      yields entries, `next_links` non-empty, `content_md` well above the length
      floor, verdict `ok`. Record the before/after side by side.
- [ ] 6.2 Re-run `--only listing --axis next_links --mode detail` on a
      subscription provider (ADR-0016). **A non-move is information, not
      failure** (D5) — this is the fourth blocker found on
      `listing-answer-always-leaves-an-index` and there is no basis for
      believing it is the last. Report what moved and what did not.
- [ ] 6.3 The arXiv cells now exercise a handler that was dead, so their
      before/after numbers are NOT a regression comparison. Say so explicitly
      rather than presenting a delta.
- [ ] 6.4 Check whether the handler now beating the browser is actually better.
      Handler output is terse and structured; browser output is prose with 484
      links. Cheaper and faster is not automatically better, and the bench is
      what says which.

## 7. Close the loop

- [ ] 7.1 BACKLOG: the remaining regex-over-markup handler sites, scoped by
      task 1.2's split (of ten files calling `re.compile`, an unknown subset). Named so the pattern is not lost — the failure mode the
      trafilatura funnel exists to prevent.
- [ ] 7.2 BACKLOG: `record_mine` returns `None` on a `<dl>/<dt>/<dd>` listing.
      A definition-list listing is a real and common shape, and this is why the
      digest gate declined on arXiv even with 484 links available. Shelf
      promotion candidate; wants a second example first.
- [ ] 7.3 BACKLOG or CLAUDE.md: the captured-not-hand-written fixture rule. It
      now has a named instance in this repo, which is the bar the repo sets for
      turning a lesson into a rule.
