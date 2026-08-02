# Transport discipline — one client, and the two tiers that are not

**Every tier and handler calls `http_fetch.fetch_bytes`.** No hand-rolled
`httpx.AsyncClient`, no inline `curl_cffi` session. Enforced by
`tests/architecture/test_transport_discipline.py`, which runs in `make check`.

## Why it is a rule

It started as a correctness argument and became a stronger one.

The original reason was the linux.do incident: a handler forked its own
`httpx.AsyncClient`, its unit tests monkeypatched *that fork's* `.get`, and
production silently served a Cloudflare anti-AI banner while the suite stayed
green. Routing everything through the primitive means the test seam **is** the
transport seam.

The stronger reason surfaced on 2026-08-02. `tests/eval_replay/harness.py`
patches `fetch_bytes` at every import site — that patch is the entire mechanism
making the replay corpus offline and deterministic. The jina tier hand-rolled a
client, so the patch could not see it, and **every replay of a case whose ladder
reached jina made a live HTTPS request to `r.jina.ai`** — in CI, on every push,
for as long as the corpus had existed. `CassetteMiss`'s promise that "replay
refuses to hit the network" was false for that tier, and the blessed
`jina:paywall` step in `regression/akakce-cloudflare-bot-wall` was a live
response rather than frozen bytes.

Measured before being believed: a `socket.getaddrinfo` spy over one replay run
reported exactly one lookup, `r.jina.ai`.

A forked client is therefore not a local style choice. It silently removes a
tier from the offline test harness, and the harness cannot tell you it happened.
`tests/eval_replay/conftest.py` now fails any live DNS lookup during a replay,
so the *next* one is loud — but the rule above is what prevents it.

## What the primitive gives you

- Chrome120 TLS impersonation (`curl_cffi`) — without it, Cloudflare-fronted
  hosts serve an anti-AI banner instead of the payload.
- Proxy plumbing via `state.proxy_pool` when a route rule matches.
- A per-host circuit breaker via `state.breakers` — one that **opens**, from
  `http-fetch` v0.3.0 onward. Before that it silently never did (ledger 0081).
- Closed-verdict mapping (`FetchVerdict` → `Verdict`), so no raw transport
  exception escapes into the orchestrator.
- Visibility to `patch_fetch_bytes`, i.e. an offline replay.

## Whose host is the breaker keyed on?

**The host the tier actually dials, never the requested target.**

`raw.py` keys on the target, correctly — it dials the target. `jina.py` keys on
`r.jina.ai`, and the paid tiers on `api.zyte.com` / `api.firecrawl.dev`, because
that is what *they* dial. Keying a fallback tier on the target host would share
the raw tier's breaker, so a host that just failed on raw would short-circuit
the fallback before it was tried — the ladder's second rung disabled by the
first rung's failure, which is the opposite of what a fallback is for.

The same question decides verdict mapping. `FetchVerdict.dns_error` means *the
name being dialled did not resolve*; `Verdict.dns_error` is terminal by design
(the planner leaves it alone — a real browser cannot resolve a nonexistent
domain either). `raw.py` passes it through; `jina.py` maps it to
`connection_error`, because on that tier the unresolvable name is the reader.
Passing it through would report a dead target on evidence about `r.jina.ai` —
an ADR-0009 laundering in the direction that silences the fetch.

## The two exceptions: `zyte` and `firecrawl`

Both POST to an authenticated vendor JSON API. `fetch_bytes` is GET-only, so the
question was whether to widen it. **Decided: no.**

The case for widening is that a bound re-implemented N times is the one missing
from the N+1th — a principle this repo applies to timeouts and means. But the
list of what these two would actually gain by routing through the primitive is
empty or negative:

| gain | zyte / firecrawl |
|---|---|
| TLS impersonation | pointless — you authenticate to the API with a key |
| proxy plumbing | both explicitly `del proxy_url`; the vendor owns egress |
| conditional GET | does not apply to a POST |
| closed `FetchVerdict` | **a loss** — no `paid_auth_error` member (see below) |
| circuit breaker | the one real gain — taken directly instead |
| `patch_fetch_bytes` visibility | neither is reachable in a replay (key-gated) |

The verdict row is decisive. `paid_verdict_for_status` maps 401/402/403 to
`Verdict.paid_auth_error` — a bad key or exhausted billing, which ADR-0009 names
explicitly as the one case that substitutes for the `try_user_browser` klaxon.
`FetchVerdict` has no such member, so routing these through the shared enum
would collapse "your key is wrong" into a generic connection failure. Widening a
GET primitive to POST in order to make a tier *less* truthful is a bad trade.

So the breaker — the only genuine gain — is taken directly, via
`_paid.paid_api_breaker`, and the exception is written down here and enforced as
a named entry in the architecture test's `_EXEMPT` table. Two further tests keep
that entry honest: one fails if an exempt module stops importing a transport
module at all (a stale entry silently pre-authorises the next module to take
that name), and one fails if an exempt tier stops calling `paid_api_breaker`
(the compensating control the exemption was granted for).

**If a third POST consumer appears**, revisit — at three, add a sibling
`post_json` to the shelf's `http-fetch` sharing the breaker and timeout
machinery, rather than widening `fetch_bytes` itself. The package's identity is
"one HTTP-GET primitive"; a second function is honest, an overloaded first one
is not.
