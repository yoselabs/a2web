# a2kit feedback — round 16 (2026-07-05)

> **Status: OPEN — blocks `deployable-container-ci` group 5 (endpoint auth).**
> a2web operator chose "GoogleAuth in a2kit first": add the `GoogleAuth`
> AuthSpec upstream, bump the a2web pin, then a2web wires
> `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`. Until then the container ships
> **open** (documented Tailscale/private-LAN-only) — no auth on the HTTP MCP
> endpoint.

## Ship the `GoogleAuth` AuthSpec (advertised in docs, absent from the package)

**Ask.** Implement + export `a2kit.packages.auth.GoogleAuth` — a concrete
`AuthSpec` wrapping FastMCP's Google OAuth provider, targeting the MCP HTTP
surface — so an author can protect a networked MCP endpoint with:

```python
class A2Web(a2kit.App):
    name = "a2web"
    routers = (WebRouter, CookiesRouter)

def build_app() -> A2Web:
    app = A2Web()
    ...
    if settings.google_client_id and settings.google_client_secret:
        app.auth(GoogleAuth(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            # base_url / redirect derived from the serve host, or explicit
        ))
    return app
```

**The gap today (v0.49.1).** `a2kit.packages.auth`'s own module docstring
advertises `GoogleAuth` as one of the "bundled concrete wrappers (`APIKeyAuth`,
`JwtAuth`, `GoogleAuth`)", and `spec.py` references `GoogleAuth` in prose — but
the symbol is **not exported and not implemented**:

```
$ python -c "import a2kit.packages.auth as a; a.GoogleAuth"
AttributeError: GoogleAuth        # also: JwtAuth  -> AttributeError

# only these resolve:
APIKeyAuth  -> OK
TokenAuth   -> OK
```

`packages/auth/_providers/` contains only `api_key.py`. So the registration
mechanism is real and works — `App.auth(spec)` accumulates specs, HTTP runs
them in registration order, MCP honours the first OAuth-targeting spec (single
FastMCP `auth=`) — but there is **no OAuth AuthSpec to hand it**. The docstring
promises a capability the package doesn't ship.

**Why this belongs in a2kit (not a2web).** OAuth-provider wiring against
FastMCP's `auth=` seam is a **substrate** concern — every MCP app served over
HTTP faces the same open-port problem, and the FastMCP provider surface is
exactly what a2kit's auth package exists to wrap (it already wraps API-key/JWT
verification). a2web hand-rolling a Google OAuth middleware would duplicate
substrate and couple a2web to FastMCP internals the auth package is meant to
hide. This is the same substrate-vs-product line the Constitution draws.

**Two clean options:**

1. **Full `GoogleAuth`** — the advertised wrapper (client id/secret + derived
   redirect), targeting MCP. Matches the docstring; unblocks the container's
   original auth ask directly.
2. **If OAuth is further out:** at minimum make the docstring honest (drop
   `GoogleAuth`/`JwtAuth` from the "bundled" list until they ship) so authors
   don't build against a phantom. `TokenAuth`/`APIKeyAuth` already ship and
   could protect the endpoint with a bearer token as an interim — but the
   operator specifically wants Google, so this is a fallback, not the ask.

**Acceptance.** `from a2kit.packages.auth import GoogleAuth` resolves;
`app.auth(GoogleAuth(client_id=..., client_secret=...))` on an HTTP MCP surface
rejects an unauthenticated request (401/redirect) and admits a valid Google
principal into the per-call DI scope (the existing `_principal_bridge` path).

## What a2web ships in the meantime

- Container `CMD` binds `--host=0.0.0.0` with **no auth**. README Deployment
  section states plainly: do **not** expose the port publicly — run it behind
  Tailscale or a private LAN until the auth rung lands.
- `deployable-container-ci` group 5 tasks are marked **BLOCKED (a2kit round 16)**
  rather than implemented, so the change doesn't claim an auth guarantee it
  can't keep (never-silently-miss, applied to the deploy contract).
