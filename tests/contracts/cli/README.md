# CLI goldens — the pre-sunset Typer surface, frozen

These are the **inherited** behaviour of `a2web`'s CLI as a2kit generated it,
captured at commit `d2dc5d8` (the last commit where that CLI still ran). They
exist because the sunset's Phase 5 rewrites the CLI by hand, and the CLI was
entirely ungated: 1236 tests, not one of which invoked it. Every byte of it —
the command tree, the flag names, the compact-JSON separators, the exit codes —
was inherited and unasserted, so a hand-written replacement would have been an
unverifiable rewrite of a surface the user drives daily.

Capturing first turns Phase 5 from "rewrite and hope" into "rewrite and diff".

## How they were captured

`_captured_with.py` is the harness, preserved verbatim rather than described,
because the exact stubbing is what makes the numbers reproducible. It ran in a
git worktree detached at `d2dc5d8` with a2kit installed, driving the CLI
in-process through `a2kit.run(app, argv)`.

Four things had to be pinned to make the capture deterministic — a first pass
without them differed run-to-run:

| Varies | Why it is not contract | Handling |
|---|---|---|
| `fetched_at` in the content wrapper | wall clock | frozen to 2026-01-01 |
| the extractor's answer | a live LLM call — the first pass actually spent quota and produced prose that would never reproduce | stubbed to a fixed `ExtractionResult` |
| `argv[0]` in Click usage lines | in-process capture reports the harness, a real run reports `a2web` | rewritten to `a2web` |
| `started_at` / `*_ms` under `--debug` | machine speed | scrubbed to `<scrubbed>`; their *presence* is still asserted |

Verified by capturing twice into different directories and diffing: identical.

## What these goldens are NOT

They are a record of **today's behaviour, warts included** — not a statement
that the behaviour is correct. Several captured quirks are things Phase 5 should
deliberately change rather than faithfully port; a delta against a golden is a
prompt to make a decision, not automatically a bug. Known ones:

- **`~95%%`** — a stray escaped percent in the `query` / `fetch_raw` docstrings
  that has no `%`-formatting consumer. It leaks into `--help` *and* into the MCP
  tool description, so every agent reading a2web's tool list has seen `95%%`
  since v0.10 (`797772f`). Fixing it is a wire delta and needs its own slug.
- **`--json` is a no-op** for both web tools — byte-identical output to the
  default. It is a2kit's end-to-end-JSON flag, and these tools already emit JSON.
- **`--format [auto|json|tsv|page-tsv]`** — a2kit formatter surface. `auto`
  produced plain JSON here (`headings` as a nested array), never TSV, so three
  of the four values were unreachable in practice on these tools.
- **`--link-roles TEXT` renders as "JSON value."** — a2kit's field-to-Typer
  conversion drops the real description for non-scalar types.
- **`serve`'s flags are almost all framework** (`--code-mode`, `--compact`,
  `--tools`, `--select`, `--internal-uds`). Only `--transport` / `--host` /
  `--port` describe anything a2web still does.

Deltas are accepted the same two-phase way as the MCP wire goldens: a run with
`A2WEB_ACCEPT_WIRE_DELTA=<slug>` rewrites the golden and appends the diff to
`tests/contracts/DELTAS.md` under that slug. There is no blanket bless.
