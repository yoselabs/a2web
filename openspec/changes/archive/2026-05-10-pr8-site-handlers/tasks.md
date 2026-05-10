# Implementation Tasks

## 1. arxiv handler

- [ ] 1.1 Create `src/a2web/handlers/arxiv.py` with URL match for `arxiv.org/abs/<id>` (and pdf post-rewrite tolerated)
- [ ] 1.2 Implement export API call (`https://export.arxiv.org/api/query?id_list=<id>`) returning Atom XML
- [ ] 1.3 Parse Atom XML with stdlib `xml.etree.ElementTree`; surface title, authors, abstract, categories
- [ ] 1.4 Render pre_rendered markdown: `# title` → byline → abstract → `## Categories`
- [ ] 1.5 Tests: happy path with offline fixture, 404, malformed XML

## 2. wikipedia handler

- [ ] 2.1 Create `src/a2web/handlers/wikipedia.py` with URL match for `*.wikipedia.org/wiki/<title>`
- [ ] 2.2 Extract language code from subdomain; call REST API `https://<lang>.wikipedia.org/api/rest_v1/page/html/<title>`
- [ ] 2.3 Run trafilatura on the Parsoid-cleaned HTML; extract title from URL slug
- [ ] 2.4 Pre_rendered markdown with title + headings
- [ ] 2.5 Tests: happy path, 404, redirect handling (canonical title differs from slug)

## 3. github handler

- [ ] 3.1 Create `src/a2web/handlers/github.py` with URL match for repo / issue / pull
- [ ] 3.2 `A2WEB_GITHUB_TOKEN` plumbed via settings; sent as `Authorization: Bearer <token>` when set
- [ ] 3.3 Repo path: `/repos/{owner}/{repo}` + `/repos/{owner}/{repo}/readme`; render metadata table + README
- [ ] 3.4 Issue path: `/repos/{owner}/{repo}/issues/{n}` + `/comments`; render title + body + threaded comments
- [ ] 3.5 Pull path: `/repos/{owner}/{repo}/pulls/{n}` + `/reviews` + `/comments`; render title + body + reviews + comments
- [ ] 3.6 Pre_rendered markdown for each shape; closed-enum verdicts on rate_limited (429), not_found, etc.
- [ ] 3.7 Tests: happy path for each shape with offline fixtures, 404, 429 rate limit, no-token vs token paths

## 4. Registration + settings

- [ ] 4.1 Add the three handlers to `_HANDLERS` in `handlers/__init__.py`
- [ ] 4.2 Export classes from package
- [ ] 4.3 Add `github_token: str = ""` to `AppSettings`
- [ ] 4.4 Settings YAML exclusion list updated to drop `github_token` (env-only)
- [ ] 4.5 Tests: handler dispatch order; non-matching URLs fall through to raw

## 5. Gate

- [ ] 5.1 `make lint` clean
- [ ] 5.2 `make ty` clean
- [ ] 5.3 `make test` green, coverage ≥85%
- [ ] 5.4 Update `CLAUDE.md` (PR8 handlers list updated; deferred handlers noted)
- [ ] 5.5 Commit `PR8: arxiv + wikipedia + github handlers`
- [ ] 5.6 Archive change via `openspec archive pr8-site-handlers`
