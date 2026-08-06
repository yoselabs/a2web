## 1. Code

- [x] 1.1 In `src/a2web/fetcher_response.py`, guard the `thin_content` assignment (~line 1002) so it is set only when `content_md` will be absent from the wire for this response (i.e. `not include_content`), applying to both the `content_thin`-hint trigger and the `empty_confirmed` (promoted-ok) trigger.
- [x] 1.2 Confirm no other read site (`wire.py`, `routers.py`, CLI derivation) assumes `thin_content` is present whenever `content_thin`/`empty_confirmed` fires independent of `include_content`.

## 2. Docs

- [x] 2.1 Add a clarifying note to `docs/adr/0015-the-withheld-body-index.md` stating `thin_content`'s index-forcing rationale is conditional on the body being withheld (per-call, not only the global-default re-evaluation trigger already listed).

## 3. Tests

- [x] 3.1 Add a test to `tests/capabilities/retrieval_completeness/test_thin_semantics.py` covering `include_content=True` + `thin_unverified`/`empty_unverified`: assert `content_md` present, `thin_content` absent.
- [x] 3.2 Add a test covering `include_content=True` + promoted-empty (`empty_confirmed`) outcome: assert `content_md` present, `thin_content` absent, synthetic answer and `content_empty` hint unchanged.
- [x] 3.3 Confirm existing `include_content=False` scenarios in the same test file still pass unmodified (regression guard for D1/D2 in design.md).

## 4. Verification

- [x] 4.1 Run `make check` (lint + ty + test + coverage + architecture guards) and confirm green.
- [x] 4.2 Re-run the specific fixture from a2web-y5m (Trendyol/akakce thin-archive case) via `mcp_client` or CLI to confirm the wire no longer duplicates the body when `include_content=True`.

## 5. Close-out

- [ ] 5.1 `bd update a2web-y5m --set-metadata branch=<branch> --set-metadata commit=<sha>` once implemented.
- [ ] 5.2 Run `/opsx:sync` or `/opsx:archive` per project convention once tests are green, to fold the `ask-response` spec delta into `openspec/specs/ask-response/spec.md`.
