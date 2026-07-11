## 1. Prompt

- [x] 1.1 Strengthen the `also_here` clause in `_ROUTER_SCHEMA_DOC`: define "covered" as covered-the-PAGE, add the narrow-ask-on-rich-page rule, keep the listing carve-out + thin-page escape.
- [x] 1.2 Bump `EXTRACT_ROUTER_V1` version 6 → 7; update the version-history comment.

## 2. Verify

- [x] 2.1 `make check` green (lint + ty + test, coverage ≥85%).
- [x] 2.2 Live spike on `koctas-product-narrow-ask-index` (subscription provider): confirm `also_here` now populates with terse query-grammar entries, no metered spend.
