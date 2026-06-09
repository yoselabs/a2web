# akakce-cloudflare-bot-wall — reference answer

**Correct behavior (what a faithful pipeline must do):**

> The page could not be retrieved (Cloudflare bot-wall). Report the
> failure honestly: `status: failed`, **no answer**, no fabricated price.

The URL is a Turkish price-comparison page for the Smartmi Fan 3. It sits
behind a Cloudflare **interactive Turnstile** challenge. Every fetch tier is
blocked: raw → `429` (verdict `rate_limited`), Wayback CDX + archive.ph →
timeouts. No content reaches the extractor, so the LLM is **never called**
(`_phase_extract_answer` short-circuits on a non-ok verdict).

## What this case guards (failure class B)

The valuable, deterministic property: **a2web never fabricates a price for a
page it could not fetch.** A bot-wall is *"couldn't see it"*, NOT *"the
product has no price / is not for sale"* — the two must never be conflated.
The contract asserts `status: failed` + `answer_present: false`: the pipeline
fails loudly and emits no answer, rather than guessing a price from the
challenge HTML.

## Why this is NOT the "Haiku reads an empty seller list and says no price" case

That was the original intent, but akakce cannot exercise it — a **two-layer**
Cloudflare block, both deferred to the CF work
(`docs/architecture/cloudflare-handling.md`):

1. **Fetch layer.** The browser tier launches Camoufox `headless=True`, which
   cannot run CF's managed-challenge JS; and akakce's challenge is
   *interactive* (a human Turnstile click cleared it in a headful probe), so
   even headful won't auto-pass.
2. **Routing layer.** Even with a cleared DOM frozen in hand, the orchestrator
   never routes here to the browser tier: the raw `429` is classified
   `rate_limited` (advances to jina, no content gate), and jina's text reader
   strips the `cf-turnstile` markers — so `block_detector`'s turnstile→browser
   escalation never fires. Confirmed empirically: feeding the cleared
   out-of-stock DOM through the real orchestrator yields `tier: jina`,
   `extractor called: False`.

The genuine "no current price" specimen (the cleared page *is*
`AggregateOffer / OutOfStock / offerCount 0 / price 0`, with price-*history*
"TL" numbers as a fabrication trap) is captured in the CF note for when the
browser path is productized.
