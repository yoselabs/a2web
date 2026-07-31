## Why

ADR-0009 says a failed fetch must never be mistakable for a complete one. Five
paths currently violate it, each verified first-hand on 2026-07-31 — and every
one of them fails in the same direction: **the caller is told less than a2web
knows, and what it is told reads as success.**

The sharpest is on the wire itself. `wire._derive_columns` builds TSV headers
from the *first row's keys only*, while `OperatorHint._omit_default_severity`
drops `severity` when it is the default `info`. So an `info` hint followed by a
`critical` one produces a table with no `severity` column, and the `critical`
value is discarded. Executed against the real encoder:

```
>>> encode_envelope({"answer": "a", "operator_hints": [
...     OperatorHint(code="cookies_stale", message="m1", fix="f1"),
...     OperatorHint(code="try_user_browser", message="WALL",
...                  fix="use your browser", severity="critical")]},
...     tsv_fields_for("query"))
{"answer":"a","operator_hints":"code\tmessage\tfix\n
cookies_stale\tm1\tf1\ntry_user_browser\tWALL\tuse your browser\n", ...}
```

`try_user_browser` is ADR-0009's loudest signal — the klaxon that says *a wall
stopped us, go look yourself*. It reaches the agent stripped of the very field
that marks it critical. `structured_content` is unaffected, which is why ~1350
field-presence assertions never caught it: they all read `call_wire`, never
`call_text`. The agent reads `call_text`.

Why now: these are days of work, they are independent of each other and of the
T1/T2 refactors, and doing them first means the decomposition is not
simultaneously a bug fix and a move — the failure mode v0.23 already
demonstrated.

## What Changes

- **TSV columns become the union of all rows' keys**, first-seen order, instead
  of the first row's keys. Collapses the three hand-rolled conditional-column
  helpers in `models.py` (`_next_links_tsv`, `_other_pages_tsv`, `_links_tsv`)
  into one rule — today the third one dissents by having no conditional at all.
- **`github.py` stops laundering degradation into `Verdict.ok`.** Six
  `except gidgethub.GitHubException: <var> = None` sites currently render a
  repo/issue/PR page as if the missing part were genuinely absent. A
  rate-limited comments fetch and an issue with no comments are indistinguishable
  to the caller.
- **`_fetch_old_reddit` calls `challenge_verdict`**, the wall check its two
  siblings (`twitter.py:221`, `wikipedia.py:97`) already run. It GETs HTML and
  runs trafilatura exactly as they do, and returns `Verdict.ok` for anything that
  extracts to prose — including a snooserv interstitial.
- **`paid_auth_error` gets the operator hint three places already claim it has.**
  `fetcher_response.py:391` seeds `retrieval_incomplete` for it *because* it
  "keeps its OWN dedicated hint"; `fetcher.py:1994` and
  `tests/architecture/test_terminal_hint_coherence.py:33` repeat the claim. No
  such hint is constructed anywhere. A bad paid key yields `failed` +
  `retrieval_incomplete` with nothing naming the fix, which CLAUDE.md's
  never-clause explicitly requires.
- **The `a2effect` taxonomy becomes reachable.** `except AppError` in
  `guard_tool` never fires: a2web imports `a2effect` in exactly one file and
  raises none of its five error types, so every tool failure is quarantined into
  `UnexpectedDefect`. A missing LLM key and a null-deref render identically. The
  handful of genuine operator/config errors a2web already raises
  (`LLMNotAvailable`, `ResourceUnavailable`) get typed.

Not breaking. Every change makes a currently-silent failure louder; no success
payload changes shape.

## Capabilities

### New Capabilities

None. Each of these is a requirement the existing capabilities already imply
but do not state precisely enough to have caught the defect.

### Modified Capabilities

- `fetch-response`: the agent-facing `content[0].text` channel must preserve
  every field present on any row of a TSV-encoded list — stated as a
  requirement, because the `structured_content`-only assertions are what let
  this survive.
- `retrieval-completeness`: `paid_auth_error` must carry an operator hint naming
  the fix; a handler that degrades a sub-fetch must not report `ok` as though
  the missing part were absent from the source.
- `site-handlers`: a handler that retrieves HTML and extracts prose must run the
  shared challenge check before returning `ok`.
- `app-composition`: tool errors that are operator/configuration faults must
  reach the wire as their typed `a2effect` class, not as `UnexpectedDefect`.

## Impact

- `src/a2web/wire.py` — `_derive_columns`
- `src/a2web/models.py` — the three `*_tsv` helpers
- `src/a2web/handlers/github.py` — six degrade sites
- `src/a2web/handlers/reddit.py` — `_fetch_old_reddit`
- `src/a2web/fetcher.py`, `src/a2web/fetcher_response.py` — the paid hint
- `src/a2web/error_wire.py`, `src/a2web/state.py`,
  `src/a2web/packages/llm_extract/errors.py` — typed errors
- `tests/architecture/test_terminal_hint_coherence.py` — its `None` allowlist
  entry for `operator_error` is justified by a comment describing a hint that
  does not exist; it must stop being an allowlist entry.
- No dependency changes. `a2effect` is already a direct dependency.
