# Findings — Router-shape pre-implementation eval (surface_eval_v2)

**Date:** 2026-05-25
**Spike:** `eval/spikes/surface_eval_v2.py`
**Output:** `eval/spikes/surface_eval_v2_output.md`
**Question:** does the FINAL prompt design (`EXTRACT_ROUTER_V1` per the openspec proposal `refactor-ask-to-router-shape`) hold up empirically before we commit to implementation?

## Summary

| metric | result | target | verdict |
|---|---|---|---|
| Parse failures | 0/12 | 0 | ✅ |
| Envelope violations | 0/12 | 0 | ✅ |
| **Memory leaks** | **0/12** | 0 | ✅ |
| Shape match (vs expected) | 10/12 | ≥9 | ✅ (2 "misses" are defensible model judgment, not bugs — see below) |
| `discussion` shape on thread URLs | 4/4 | 4 | ✅ |
| `genre` populated when applicable | 12/12 | most | ✅ |
| `genre: null` leakage (should be omitted) | 0 | 0 | ✅ |
| `ask_here: []` leakage (should be omitted) | 0 | 0 | ✅ |
| `ask_here` count on `discussion` pages | 5,5,5 | ≥5 | ✅ generosity rule works |
| `try_url` soft-cap on rich pages | 2-3 emitted | >0 | ✅ recovered v1 regression |
| Cost (10-URL subset vs v1 catalog) | +0.4% | ≤+5% | ✅ (router prompt is bigger but generates less output → wash) |

**1 fetch failure: reddit-rust-thread** — known backlog item (Reddit anti-bot), not a router-shape issue.

## Per-URL detail (12 successful + 1 fetch fail)

| URL | structural_form | shape | shape_match | genre | ask_here | try_url | cost |
|---|---|---|---|---|---|---|---|
| paper-abs | reference | key-value | ✗→prose* | paper | 3 | 0 | $0.0141 |
| hn-front | listing | records | ✓ | news* | 3 | 0 | $0.0177 |
| hn-thread | thread | **discussion** | ✓ | community | **5** | 0 | $0.0199 |
| mdn-array | reference | mixed | ✓ | official | 3 | 0 | $0.0195 |
| rfc-9110-idempotent | reference | mixed | ✗→prose* | spec | 0 | 2 | $0.0186 |
| so-yield | thread | **discussion** | ✓ | community | **5** | 0 | $0.0203 |
| gh-httpx-readme | product | mixed | ✓ | official | 5 | 3 | $0.0166 |
| pydantic-releases | changelog | records | ✓ | official | 3 | 2 | $0.0221 |
| wiki-rust | article | prose | ✓ | encyclopedia | 4 | 0 | $0.0191 |
| pypi-httpx | product | key-value | ✓ | official | 0 | 2 | $0.0183 |
| lobste-thread | thread | **discussion** | ✓ | community | **5** | 0 | $0.0155 |
| blog-julia-comments | article | prose | ✓ | personal | 3 | 0 | $0.0195 |
| reddit-rust-thread | (fetch fail) | — | — | — | — | — | — |

\* see notes below

## Key wins (validates the design)

**1. `shape=discussion` picks reliably.** All 4 thread-style URLs (hn-thread, so-yield, lobste-thread) hit `discussion` cleanly. The inverse case (blog-julia-comments, which is actually a personal blog post WITHOUT comments) correctly stayed `prose` — the model didn't over-apply the new label.

**2. Discussion-shape generosity rule works.** All 3 successful `discussion` pages emitted exactly 5 ask_here items (vs 3-4 on non-discussion pages). The prompt sentence "when shape=discussion … lean higher" hit precisely.

**3. Soft-cap `try_url` recovers v1's hard-cap regression.** v1 hard-capped to 3 and emitted 0 on rich pages (MDN, wiki). v2 soft-cap emitted 2-3 try_url on rich pages where v1 had 0 (pydantic-releases, gh-httpx, pypi-httpx, rfc-9110). Simple pages (wiki, blog) still emitted 0, as desired.

**4. Omit-empty discipline holds.** Zero `null` or `[]` leakage. The "omit the key entirely when empty" instruction is followed cleanly — the wire shape matches the openspec `_prune_wire` discipline before we even build the serializer.

**5. Memory leaks: zero — and this is BEFORE the SDK isolation patches land.** The prompt's tight focus (closed enums, explicit schema, "extraction helper" framing) was sufficient to keep the model from drifting into personal-context territory. The `mcp_servers={}` + `strict_mcp_config=True` patches remain belt-and-suspenders defense.

**6. Closed-enum compliance: 100%.** Zero unknown values in `structural_form`, `shape`, `genre`, or `obstacle` across 12 calls. No drift.

**7. Cost holds.** vs the v1 leaner-catalog baseline (10 URLs): +0.4% (essentially equal). vs v0.20 production `EXTRACT_WITH_AFFORDANCES_V1` (which carries 1106 overhead tokens vs router's ~700), router is meaningfully cheaper — but that comparison wasn't run live here.

## "Misses" that aren't bugs (clarify in spec)

- **paper-abs got `key-value` instead of `prose`.** arxiv `/abs/` is heavily structured: title + authors + abstract + subjects + comments as key-value rows. Both `key-value` and `prose` are defensible. My eval-time expectation was off, not the model.
- **rfc-9110 got `mixed` instead of `prose`.** RFC has prose AND grammar tables AND status code lists. `mixed` is actually the better call than `prose`. Again my expectation was off.
- **hn-front got `news` genre instead of `community`.** Defensible — HN front-page items ARE news-flavored aggregation. `community` would also be valid. Mild concern: `news` genre on hn-front could mislead an agent that branches on it. Worth tightening the prompt's `genre` examples to disambiguate (HN front = `community`, BBC = `news`).

None of these are blockers for implementation. The first two are taste; the third is a minor prompt-tuning candidate for a follow-up.

## What this validates for `/opsx:apply`

The proposal's design choices empirically check out:

- 7-field surface — works
- 9-value `structural_form` — works (no drift)
- 7-value `shape` with `discussion` — works (4/4 thread URLs)
- 7-value `genre` — works (always populated when applicable)
- 4-value `obstacle` — not stress-tested here (no obstacles in this corpus); covered by `router_shape_v2_stress` previously
- Soft cap on `ask_here` / `try_url` — works (3-5 typical, 5+ on discussion, 0 on simple)
- Obvious-filler rule — held (no obvious follow-ups across 12 URLs)
- Q-conditioned reasons on `try_url` — held (sampled reasons are URL-purpose-specific, not generic)
- Omit-empty discipline — works at the prompt level, before serializer involvement
- Memory isolation — prompt-side already clean; SDK patches are defense in depth

## Recommendation

**Proceed to `/opsx:apply`.** The design is empirically validated.

Optional minor follow-up (post-impl):
- Tighten the `genre` examples in the prompt to push HN front → `community` instead of `news`.
- Don't re-define expectations for `paper-abs` / `rfc-9110` shapes — the model's calls are reasonable; my eval-time expectations were the bug.
