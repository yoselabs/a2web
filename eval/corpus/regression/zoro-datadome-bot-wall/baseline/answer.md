# zoro-datadome-bot-wall — reference answer

**Correct behavior (what a faithful pipeline must do):**

> The page could not be retrieved (DataDome bot-wall). Report the failure
> honestly: `status: failed`, **no answer**, no fabricated price or stock claim,
> and a critical `try_user_browser` hint.

The URL is a US industrial-supply product page for a Dayton air circulator. It
sits behind a **DataDome** interactive CAPTCHA. Every retrieval path is blocked
and each is frozen in `inputs/`:

| rung | outcome |
|---|---|
| raw (curl_cffi impersonation) | `403`, `x-datadome: protected` |
| jina (`r.jina.ai` reader) | `403` — the reader is walled at the same edge |
| browser | rendered, 1525 bytes: a `geo.captcha-delivery.com` CAPTCHA iframe |

No content reaches the extractor, so the LLM is **never called** — there is no
`inputs/llm/` and there must not be one.

## What this case guards (failure class B)

**a2web never fabricates a price or an availability claim for a page it could
not fetch.** A bot-wall is *"couldn't see it"*, NOT *"the product has no price /
is not for sale"* — conflating the two is the ADR-0009 harm in its commerce
form, where the wrong answer looks like a real one. The contract asserts
`status: failed`, `tier: none`, `has_content: false`, and the critical
`try_user_browser` hint: the pipeline fails loudly rather than reading a price
out of challenge markup.

## Why this case replaced `akakce-cloudflare-bot-wall` (2026-08-02)

akakce stopped being a wall **for a2web specifically**. A plain client still gets
a Cloudflare `403 cf-mitigated: challenge` from it, but the raw tier's curl_cffi
impersonation now passes that challenge in one hop, so the case measured a
success while claiming to guard a failure. It was re-blessed as
`akakce-no-current-price`, which is the specimen its own notes said it could not
provide.

This case is a **strictly stronger** guard than akakce ever was, on the axis the
old notes conceded:

- akakce's raw `429` classified as `rate_limited`, which advances to jina without
  a content gate, and jina's text reader stripped the `cf-turnstile` markers — so
  `block_detector`'s turnstile→browser escalation **never fired**. The old case
  could not reach the browser rung at all, and said so.
- Here the browser rung **runs and is frozen**, so the case exercises the full
  ladder and the honest-failure floor at its end, rather than stopping two rungs
  short of it.

It also widens vendor coverage: every other wall specimen in the corpus is
Cloudflare. DataDome fails differently — a `403` with a JS/iframe CAPTCHA body
rather than an interstitial with a `Just a moment...` title — and a
fingerprinting suite that only ever saw Cloudflare is a suite that can be tuned
to one vendor's markers without noticing.
