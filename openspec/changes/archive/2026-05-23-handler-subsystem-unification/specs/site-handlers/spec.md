## ADDED Requirements

### Requirement: Handlers fetch via the shared handler-transport primitive

Every site handler SHALL perform its HTTP fetches via the shared `handler-transport` primitive (`packages/http_fetch.fetch_bytes`). Handlers SHALL NOT construct `httpx.AsyncClient` or any other ad-hoc HTTP client. This places every handler under the project's anti-bot (`curl_cffi` Chrome TLS impersonation), proxy-routing, and per-host circuit-breaker infrastructure.

#### Scenario: No handler imports an ad-hoc HTTP client

- **WHEN** any module under `src/a2web/handlers/` is inspected
- **THEN** it imports neither `httpx` nor any equivalent ad-hoc HTTP client, and its `fetch()` body issues HTTP calls via `fetch_bytes`

#### Scenario: Handler fetches reach Cloudflare-fronted hosts

- **WHEN** a handler targets a Cloudflare-fronted host (e.g. `linux.do`) and runs through `fetch_bytes`
- **THEN** the request is dispatched with Chrome TLS impersonation and reaches the real endpoint, not an anti-bot challenge page

### Requirement: Handler-rendered titles and HTML fragments use the shared converter

Every site handler that renders an HTML-bearing field — title, post body, comment body, topic excerpt — SHALL convert it via the shared `packages/html_fragment` converter: `to_text(fragment)` for plain-text fields, `to_markdown(fragment, base_url=...)` for body fields. Handlers SHALL NOT carry ad-hoc regex strippers. All HTML entities SHALL be decoded; non-breaking-space (`\xa0`) SHALL be folded to plain space; every `<a href>` in a markdown-rendered fragment SHALL be preserved as `[text](href)`.

#### Scenario: Handler-rendered title is entity-decoded

- **WHEN** a handler renders a title whose source field contains HTML entities (e.g. `fancy_title = "Can&rsquo;t add note"`)
- **THEN** `pre_rendered.title` contains the decoded character (`'`) and no raw entity (`&rsquo;`)

#### Scenario: Handler-rendered body preserves links

- **WHEN** a handler renders an HTML body fragment containing `<a href="https://e.com">link</a>`
- **THEN** the rendered markdown contains `[link](https://e.com)`

#### Scenario: No handler imports an ad-hoc HTML stripper

- **WHEN** any module under `src/a2web/handlers/` is inspected
- **THEN** it contains no module-local `_html_to_md` / `_cooked_to_md` / `_strip_html` / `_text_of` regex stripper; HTML-fragment conversion goes through the shared package
