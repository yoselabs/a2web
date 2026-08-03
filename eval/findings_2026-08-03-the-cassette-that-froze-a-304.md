# The frozen-cassette suite is not hermetic — it froze a `304` (2026-08-03)

Diagnosis of the BACKLOG entry *"the test suite writes to the developer's REAL
cache"*, whose blocked half was: setting `A2WEB_CACHE_DIR` to a temp dir turns
`tests/eval_replay/` red.

**Root cause found, complete, and it is worse than a hermeticity wart.**

---

## The finding

`eval/corpus/regression/akakce-no-current-price/inputs/raw.http` — the frozen
HTTP exchange the replay suite calls its input — records this:

```
  >>> GET https://www.akakce.com/vantilator/...,24576507.html
  status: 304
  conditional-hit: true
  --- body ---
  (13 bytes — the marker and a newline)
```

**A `304 Not Modified` carries no body by definition.** It is a pointer to a
copy the client already holds. The cassette was captured against a warm cache,
so the recorded exchange is a conditional GET whose actual bytes live in
`~/.a2web/cache.sqlite` — on the machine that captured it, and on any machine
that has since fetched that URL.

Its blessed baseline asserts the opposite:

```json
{ "has_content": true, "answer_present": true, "status": "ok",
  "steps": ["raw:ok", "extract:ok", "gate:ok"], "tokens_full_max": 3629 }
```

Content and an answer are demanded from an input that contains neither.

## Confirmed both ways

Cold cache (`A2WEB_CACHE_DIR` set at conftest module scope, so the scrub cannot
delete it), instrumented directly:

```
  tier: raw   status: ok   cache: miss
  content_len: 0
  extracted_answer: None
  cassette saw content?: False     <- the LLM cassette is never called
  narrative: raw → ok (9ms).
```

Warm cache — and the URL **is** present in the real home cache on this machine
(`select count(*) from cache where url = ...` → 1) — the same replay passes.

So `test_llm_egress_is_reproduced_byte_for_byte`, whose docstring is *"the
recorded LLM answer is replayed exactly, identically across runs"*, passes
because of state in a directory outside the repository.

## Two defects, not one

1. **The cassette is not self-contained.** The suite's determinism claim is
   false: its bytes are not frozen, they are borrowed. Anyone cloning this repo
   onto a clean machine gets a red suite for a reason no message explains, and
   the CI green is an accident of CI fetching the page live at capture-adjacent
   times or of the 304 path never being exercised there.

2. **A 304 with no cached body produced `status: ok` and an empty
   `content_md`.** That is the ADR-0009 harm in the pipeline itself, not in the
   harness: an empty result reported as success, with a cheerful narrative
   (`raw → ok (9ms)`) and no hint. It is currently only reachable when a
   conditional request is answered without a cache entry behind it — which
   should be impossible in production (a2web only sends `If-None-Match` when it
   HAS the row) but is exactly what a replayed cassette does.

Defect 2 is the more serious of the two and is independent of the test harness.

## Why the obvious fixes are each wrong alone

**Guard only** — make the cassette loader reject a recorded `304` with an empty
body as an unreplayable `CassetteMiss`. Correct, and it converts a silent wrong
guarantee into a loud failure. But it turns the suite red *immediately*,
including on `main`, because the offending cassette is committed.

**Re-capture only** — refreeze `akakce-no-current-price` against a cold cache so
`raw.http` carries a `200` and real bytes. Fixes this instance and leaves the
mechanism in place for the next capture taken on a warm machine.

**And re-capture carries its own hazard that must not be waved through.** This
case is a *fabrication-trap specimen*: it exists because the page shows no
current price, and the regression is that a2web must not invent one. A
re-capture pulls whatever akakce serves today. If the product now has a price,
the re-captured case still passes its contract while no longer testing anything
— the exact "a golden proves a surface has not changed, not that it was right"
failure this repo already has a **Never** entry for.

## What I recommend, in order

1. **Fix defect 2 first, independently.** A conditional-hit tier result with no
   cache row behind it must not gate as `ok`. This is a product fix with a
   deterministic unit test and no corpus dependency.
2. **Add the cassette guard** (`304` + empty body → loud `CassetteMiss`), and
   in the same change re-capture the one case it fails.
3. **Verify the re-captured page still has no current price** before blessing
   it — by reading the fetched body, not by trusting the contract to stay
   green. If akakce now shows a price, the case must be re-sited to another
   no-price page rather than silently re-blessed.
4. **Then** the conftest one-liner from the BACKLOG entry, which stops tests
   writing to `~/.a2web` at all.

Steps 1–3 are a change proposal, not a drive-by. Step 4 is one line and is
blocked only by them.

## Evidence

- `eval/corpus/regression/akakce-no-current-price/inputs/raw.http` — `status:
  304`, `conditional-hit: true`, 13-byte body section.
- `.../baseline/contract.json` — `has_content: true`, `answer_present: true`.
- Cold-cache instrumented run, reproduced above; 1.9s, no network, no hang.
  (An earlier attempt to reproduce this by passing `A2WEB_CACHE_DIR` on the
  command line was **invalid** — `tests/conftest.py` deletes every `A2WEB_*`
  var at import, so that run silently used the home cache and took five
  minutes for unrelated reasons. The var must be set inside conftest, after
  the scrub.)
