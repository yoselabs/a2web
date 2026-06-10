# Eval substrate — capture, replay, refresh

This directory is the **dev/test layer** for a2web's extraction-fidelity
evals. It is *not* part of the shipped `a2web` package (enforced by
`tests/architecture/test_eval_not_imported_by_a2web.py`): evals are tests,
and the product never depends on its own harness.

## What lives here

| File | Role |
|------|------|
| `cassette.py` | Serialize/parse one frozen HTTP egress (`*.http`), keyed by URL. |
| `corpus.py` | Load an on-disk corpus of cases (`eval/corpus/<corpus>/<case>/`). |
| `capture.py` | `make eval-capture` — run the real app live, freeze every egress. |
| `refresh.py` | `make eval-refresh` — re-capture, diff vs the blessed baseline, bless. |

The **read side** (`cassette.py`, `corpus.py`) is consumed by the replay
harness under `tests/eval_replay/`. The **write side** (`capture.py`,
`refresh.py`) is driven by the `make` targets.

## Why freeze at the egress boundary

Replay reads frozen bytes at each tier's **egress** — the
`http_fetch.fetch_bytes` outcome, the `BrowserPool`-rendered DOM, the
`LlmExtractorResource` response — while running the orchestrator, gate,
tier ladder, and escalation logic *unmodified*. Freezing the produced
`FetchResponse` instead would remove the very thing under test: the
decision about how hard to try. The LLM is a *recorded* egress, not a
hand-written stub, so a replayed answer and its token cost are
byte-for-byte what the real pipeline would produce from those inputs.

## Case layout

```
eval/corpus/<corpus>/<case>/
    case.yaml              # question, url, failure_class, tags, expected tier path
    inputs/                # the frozen world — MAY drift as the site changes
        raw.http           # raw/jina/archive HTTP egress (URL-keyed; may hold many)
        rendered.html      # browser-rendered DOM (when frozen)
        llm/<key>.json     # recorded LLM provider responses (when frozen)
    baseline/              # what the substrate asserts — changed only by an explicit bless
        contract.json      # deterministic shape (tier, status, tokens bound, …)
        answer.md          # reference answer for the LLM-judged axes
    meta.yaml              # per-layer capture timestamp, source URL, content hash, sizes
```

`inputs/` and `baseline/` are deliberately separate: a refresh re-captures
`inputs/` and shows the new answer as a **diff** against the blessed
`baseline/`, so an operator can tell a code-driven change from a
site-driven one before accepting it.

### LLM recording key

A case records **one** LLM response per case — a single keyed file under
`inputs/llm/` (`CassetteLlm` serves it for the case's single `extract()` call).
This is sufficient because a fetch makes exactly one extraction call.
Prompt-hash / `(url, tier)` multi-call keying is **deliberately deferred** until
a case needs more than one LLM call; none does today. The key never has to
coexist with the production `EXTRACT_*` cache prefix because the cassette
replaces the extractor egress wholesale (the cache is never consulted in
replay). A bot-walled / honest-failure case records **no** LLM file at all — the
extractor is never invoked (e.g. `regression/akakce-cloudflare-bot-wall`).

## Failure-class taxonomy (`failure_class`)

Every case declares the failure class it exercises. The breaking corpus
deliberately spans all three.

- **Class A — clean structured schema.** The data the question needs is
  present in a clean, well-formed source (JSON-LD, a table, a list). The
  pipeline should extract it cheaply and correctly. These are the controls.

- **Class B — source omits / JS-only / bot-walled.** The raw HTML does not
  contain the answer: it is rendered client-side, behind a bot wall, or
  simply absent from the markup. Answering requires escalation (browser),
  an alternate source (archive), or an honest "not available" — never a
  fabricated answer. These cases gate the escalation ladder.

- **Class C — structured data present but wrong.** The source *has*
  structured data, but it does not answer the question as asked:
  list-vs-sale price confusion, stale values, wrong locale/currency, a
  schema field that means something other than its name. These are the
  fidelity traps — the class the Hepsiburada listing bug belongs to — where
  a value-blind projection produces a confident wrong answer.

A `JS`/`spa`/`commerce` **tag** (distinct from the class) marks a case
whose browser-rendered DOM is frozen eagerly at capture, because that class
is the one that escalates and we never want a routing change to find the
browser layer missing.

## Corpuses

- `_selftest/` — hand-authored deterministic fixture; the instrument
  testing itself. No network, no LLM.
- `regression/` — cases the product has actually gotten stuck on (the
  Hepsiburada listing case lives here). These must keep passing.
- `breaking/` — cases declaring their failure class, kept as permanent
  class-spanning coverage. Holds class **A** (clean schema: `arxiv-…`,
  `allrecipes-…`) and class **B** (source omits → honest "not present":
  `wikipedia-absent-fact`). Class **C** ("structured data present but wrong")
  is covered by the `regression` cases (`hepsiburada-listing-price`,
  `recipe-nutrition-volume-gate`) rather than duplicated here — a fresh non-CF
  C is impractical to capture, since misleading-schema retailers sit behind
  Cloudflare.

## Make targets

```
make eval-capture URL=… Q=… CORPUS=regression ID=some-slug   # freeze a new case live
make eval-replay  CORPUS=regression                          # deterministic replay (offline)
make eval-refresh CASE=regression/some-slug                  # re-capture + diff + bless
```

`make eval-replay` also runs inside `make check` via the deterministic
replay tests under `tests/eval_replay/`. The capture/refresh targets are
live-network and spend LLM quota — run them deliberately.
