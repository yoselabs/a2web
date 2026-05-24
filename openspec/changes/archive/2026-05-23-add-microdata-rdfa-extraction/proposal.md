## Why

Today the `json_in_script` extractor sees the structured-data fraction of pages that ship it as JSON-in-script tags (Next.js / Nuxt app-state and LD-JSON). It does not see microdata (`itemscope` / `itemprop` / `itemtype`) or RDFa (`property=` / `typeof=`), which together cover a meaningful tail of the open web: long-tail e-commerce (Shopify-class storefronts that don't ship LD-JSON), academic publishing (RDFa-heavy), and the OpenGraph header set (carried as `<meta property="og:*">` tags rather than JSON). On these pages a2web currently has no structured surface to feed the LLM extractor — we fall back to trafilatura's content, which loses the typed product/article/itemList signal.

Adding microdata + RDFa + OpenGraph extraction closes that gap with one new dependency surface and ~40 LoC of orchestration. It also brings the structured-data pipeline closer to "all the structured data the page carries, ranked", which is the right north-star shape for the LLM-extractor's prompt.

## What Changes

- Add `extruct>=0.18,<1` as a direct dependency (transitively pulls `rdflib`, `mf2py`, `jstyleson`, `w3lib`).
- Add new `JsonSource` Literal values: `"microdata" | "rdfa" | "opengraph"`. (The implementation-only `"window_var"` value, already present in code, is also documented in the spec at this point to fix the existing code-vs-spec drift.)
- Extend `packages/json_in_script.py::extract_json_payloads(html)` to call `extruct.extract(html, syntaxes=["microdata","rdfa","opengraph"])` (via `asyncio.to_thread` at the call site in `fetcher.py` — extruct is sync, uses lxml + rdflib). Each extruct result is wrapped as a `JsonPayload(source=..., data=..., script_id=None, byte_size=<json-dump-len>)`.
- Extend `rank_payloads` with three new buckets ordered after `ld_json` strong / `next_data` / `nuxt_data`: strong-microdata, opengraph, weak-microdata, rdfa. Concrete order in design.md.
- Extend `domain.py::json_to_markdown_rows` and `_ld_json_to_markdown` with adapter cases for the three new shapes. Microdata's `Product` / `ItemList` shape is structurally similar to LD-JSON so the adapter reuses the LD walker. OpenGraph and RDFa get their own small adapters (flat key-value table for OG; rdflib's resource shape for RDFa).
- Surface the new payload sources in `Diagnostic` / LDD events as informational signals only (no operator-hint or verdict change).

Not changing: the `Handler` protocol, the orchestrator's six-phase shape, any MCP wire surface, the `FetchResponse` / `AskResponse` envelope shape, or the gate's quality logic.

## Capabilities

### New Capabilities

None — this slots into the existing `json-extract` capability.

### Modified Capabilities

- `json-extract`: the `Detect known JSON-in-script payload shapes` requirement widens — new sources, new detector calls, and a clarified note that some sources (microdata, rdfa, opengraph) are NOT script-tag-based and come through extruct. The `JSON-LD Product / Article shapes have preferred status` requirement extends to cover the new buckets. The `Package independence preserved` requirement stays in force — extruct is third-party, not an a2web import.

## Impact

- **Code**: `packages/json_in_script.py` grows by ~40 LoC (extruct call + adapter into `JsonPayload`). `domain.py` grows by ~50-80 LoC (three new shape adapters). `rank_payloads` gains 3-4 lines of bucket logic. Net: +90-120 LoC for new capability.
- **Dependencies**: `+extruct` direct; `+rdflib`, `+mf2py`, `+jstyleson`, `+w3lib` transitive. `rdflib` is the heaviest (~MB-scale).
- **Async chokepoint**: extruct is sync (lxml + rdflib parse). The extruct call SHALL be wrapped in `asyncio.to_thread` at the orchestrator call site in `fetcher.py`. The existing call to `extract_json_payloads` in `_phase_extract` already runs in the same chokepoint; widening it covers the new sources naturally.
- **Performance**: extruct's RDFa path uses rdflib, which is slow. On pages without RDFa attributes the call short-circuits cheaply. Concrete cost is measured during the implementation phase; if RDFa parsing materially regresses p50 fetch time, the change adds a `disable_rdfa` setting (defaulted on) as a follow-up.
- **MCP wire surface**: no change. The new payloads flow into the same `pre_rendered.content_md` synthetic surface via `json_to_markdown_rows`.
- **Tests**: new fixtures under `tests/fixtures/structured/` for microdata, RDFa, opengraph. New scenarios in `tests/capabilities/test_json_extract_*`. The package-independence invariant continues to pass.
- **Eval corpus**: add 1-3 corpus entries that exercise microdata-only pages (Shopify product, academic page with RDFa) to confirm the new capability lifts answer quality on the existing four-axis benchmark.
