# Output benchmark — findings, 2026-05-23 (Run 5)

Run after v0.15.0: adds the `lobste-active` corpus cell (first URL that
exercises the generic `record_extract` path; no site-handler exists for
lobste.rs) and the amended `next_links` judge prompt (don't penalize
unfamiliar entries / assume fabrication). Same provider, same judge as
Run 4 (2026-05-23, earlier today).

Run: 33 cells (was 30), $2.57, 5m42s wall. Run dir (regenerable,
gitignored): `eval/runs/2026-05-23_022317/`.

## Headline — four axes, per system

| System | quality | env tokens | clarity | contract | next_links |
|---|---|---|---|---|---|
| webfetch_baseline | 3.18 | 171 | 3.00 | n/a | n/a |
| a2web_detail | 3.64 | 3699 | 1.22 | 11/11 | 3.00 |
| a2web_extract | **4.00** | 408 | **3.78** | 11/11 | 4.00 |

## What this run was designed to show

### lobste-active cell — Phase 4 record-render WORKS

Lobsters has no site-handler, so it falls through to the generic
`record_extract` path. The rendered output is exactly the structure
Phase 4 was built for:

```
### Listing (25 records)

- [What are you doing this weekend?](https://lobste.rs/s/hwyrwd/what_are_you_doing_this_weekend)
  11 ☶ ask programming authored by caius 17 hours ago | 34 comments 34
  [11](.../login) · [ask](.../t/ask) · [programming](.../t/programming) · ...

- [C Programming Language Quiz](https://stefansf.de/c-quiz/)
  35 c stefansf.de via spc476 19 hours ago | caches Archive.org Ghostarchive | 13 comments 13
  ...

- [The Maintainer's Dilemma](https://spf13.com/p/the-maintainers-dilemma/)
  ...
```

Each row leads with `- [title](href)`, the meta line carries
tags/author/age/comment count, the heading text is NOT duplicated in the
body smush, and the remaining links render below. This is exactly the
shape the unit test pins (`test_record_markdown_leads_with_heading_link_then_body_without_duplication`).

Judge scores on this cell:

| System | overall | clarity | contract | next_links |
|---|---|---|---|---|
| webfetch_baseline | 5 | 3 | n/a | n/a |
| a2web_detail | 5 | 1 | pass | 3 |
| a2web_extract | 5 | 3 | pass | 3 |

All three systems scored 5/5 overall on the task ("list 5 most active
stories with title / tags / comment-count"). The structure-aware render
didn't degrade a2web's ability to answer; it made the underlying
`content_md` clearly more legible for the agent.

### Amended `next_links` judge prompt

Run 4 → Run 5 for `a2web_extract` next_links: 4.67 → 4.00. Within
day-on-day judge variance; the amended prompt ("don't assume
fabrication") didn't visibly shift scores up or down on the existing
cells. The point of the amendment is correctness under doubt, not score
inflation; the prior numbers stand as comparable.

## Delta vs Run 4 (earlier today, same provider/judge)

| Axis | webfetch | a2web_detail | a2web_extract |
|---|---|---|---|
| quality | 3.50 → 3.18 | 4.10 → 3.64 | 3.90 → 4.00 |
| env tokens | 206 → 171 | 3760 → 3699 | 469 → 408 |
| clarity | 3.11 → 3.00 | 1.11 → 1.22 | 3.75 → 3.78 |
| next_links | n/a | 3.00 → 3.00 | 4.67 → 4.00 |
| contract | n/a | 10/10 → 11/11 | 10/10 → 11/11 |

`a2web_extract` quality climbed to 4.00, the best of the three runs;
WebFetch and a2web_detail drifted within judge variance. Contract
remains 11/11 on both a2web systems including the new lobste cell — no
envelope regression from the Phase 4 record changes.

## What still needs work

Same as Run 4: `a2web_detail` clarity stays poor (1.22) because
full-page markdown is hard to digest, and `reddit-comments` continues to
cap that cell at the anti-bot lockout. Neither is touched by v0.15.0.

## Add to corpus (future)

- A Discourse URL (e.g. `https://meta.discourse.org/latest`) would
  exercise both the curl_cffi-impersonated transport AND the
  entity-decoded fancy_title path in the same cell — currently those
  fixes only have unit-test coverage and the manual `make handler-probe`
  assertion.

## Cost

$2.57 (vs Run 4's $2.37; +1 cell, ~$0.20).
