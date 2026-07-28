# A handler never reports `ok` on a challenge page

## Why

The probe change surfaced this and deliberately did not fix it:

```
TwitterHandler.fetch(…)  via xcancel.com   2026-07-28
  HTTP            200
  body            6822 bytes — a browser-verification interstitial
  verdict         Verdict.ok          ← the defect
  content_md      416 chars, "Checking your browser / Starting verification…"
```

`_try_instance` returns `Verdict.ok` for any 200 whose trafilatura extraction is
non-empty. A challenge page extracts perfectly well.

**The lying verdict is the smaller half.** `TwitterHandler.fetch` is the only
handler with a multi-upstream failover loop: it shuffles `nitter_instances` and
returns at the first instance reporting `ok`. So a walled instance does not
merely produce a bad result — it **shadows every instance after it in the
list**, and because the list is shuffled per fetch, which one wins is random.
With a mix of working and walled instances the same URL returns a tweet or an
interstitial depending on shuffle order.

That failure survives any upstream fix. It is a bug in the failover, not in the
choice of hosts.

## What Changes

- A handler that extracts HTML consults the block catalogue before reporting
  `ok`. A body carrying a challenge fingerprint returns a wall verdict.
- The nitter failover loop treats a walled instance as a FAILED instance and
  continues to the next one, rather than returning it as the answer.
- When every instance is exhausted and at least one was walled, the handler
  returns `Verdict.block_page_detected`.

**Two claims in the original draft did not survive their first live run**, and
the change is better for it — both are recorded at the code that fixes them:

- *"The handler's check is not gated on rendered length."* Forcing the
  catalogue's length-gated markers on turned `/wiki/Python_(programming_language)`
  into `block_page_detected`, because a cited PEP title contains "Network
  Security". Those markers are English phrases; the length floor is what makes
  them safe. The real guarantee is narrower and stated as such.
- *"…with the critical `try_user_browser` hint, reddit's `_walled_signal`
  shape."* Reddit's eager shape does not fit a tier-0 handler the cascade
  continues past: nitter was walled, the hint fired, and then jina retrieved the
  tweet — a response carrying 2204 characters under a klaxon saying it had none.
  The hint belongs to the failure floor, which knows how the cascade ended.

## Scope, and what the audit found

TWO of the nine handlers can be fed a challenge page and call it content:
`twitter` and `wikipedia` (`reddit` already fails walls loudly via
`_walled_signal`). The JSON-API handlers — `discourse`, `hn`, `v2ex`, `habr` —
are structurally immune: a challenge page is not valid JSON, so `json.loads`
already fails them into a non-`ok` verdict.

**Corrected during apply:** an earlier draft of this section said THREE and
listed `habr` as an HTML handler while ALSO listing it among the JSON-API ones.
The code settles it — habr fetches `habr.com/kek/v2/articles/…` and gates on
`isinstance(payload, dict)`, so it is JSON-only and needs no check. The
structural-immunity claim is no longer argued: `test_json_api_handler_is_immune_to_a_challenge_body`
feeds hn and habr the captured interstitial and asserts the verdict.

Only `twitter` has the failover loop, so only `twitter` has the shadowing bug.

## Impact

- `src/a2web/handlers/_common.py` — the shared challenge check.
- `src/a2web/handlers/twitter.py` — the loop, and the exhausted-all terminal.
- `src/a2web/handlers/{habr,wikipedia}.py` — the check applied.
- `tests/` — the captured interstitial is already committed and is the witness.

## The upstream question, answered

BACKLOG asked whether the twitter handler has any reachable upstream. Ten public
nitter instances were surveyed on 2026-07-28:

| outcome | instances |
|---|---|
| walled (Anubis / CF / 403) | `xcancel.com`, `nitter.tiekoetter.com`, `lightbrd.com`, `nitter.space`, `nuku.trabun.org` |
| dead / empty / error | `nitter.net` (200, 0 bytes), `nitter.privacydev.net`, `nitter.poast.org` (503), `nitter.kuuro.net` (404) |
| redirector → a walled instance | `twiiit.com` → `lightbrd.com` |

**None works.** So this change does not make the twitter handler succeed, and
does not claim to. It makes it truthful, and it fixes a failover bug that would
otherwise still be there when an upstream returns.

Retirement was considered and is NOT proposed — see design D4. Measured: with
the handler removed, the same URL degrades to `not_found` with `info`-severity
`content_not_found` hints. With the handler present and truthful it is
`block_page_detected` + `retrieval_incomplete` + a critical `try_user_browser`.
The walled answer is the more honest one, and it is the one ADR-0009 asks for.
