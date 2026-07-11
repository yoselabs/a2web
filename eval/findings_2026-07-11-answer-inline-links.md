# Hypothesis: rehydrated links IN THE ANSWER may be more useful than try_url alone (2026-07-11)

**Origin:** the reframe that flips Fable's "answer-leak" objection. The objection
assumed a `{{n}}` marker reaches the caller un-rehydrated (garbage). But if the
server runs `rehydrate_text()` over the `answer`, a handle the model wrote into
its prose becomes a REAL URL — an actionable, self-contained answer:
"reviews aren't on this page — they're at https://…-yorumlari".

**Key architectural point:** this needs NONE of the `include_links` / inline-
content machinery. It works on the current v1 **out-of-band digest**: the model
reads the digest, references `{{1}}` in its answer prose, the server rehydrates
the answer text. Orthogonal to the include_links debate.

**Shipped now (defensive, not the hypothesis):** `_phase_extract_answer` runs
`fc.link_digest.rehydrate_text(answer)` — a stray handle becomes a URL (known)
or is removed (unknown), never leaked. `{{n}}` is collision-safe so real answer
text is untouched (unit-tested in `test_link_digest.py`). This hardens v1
regardless of the hypothesis.

## The hypothesis to evaluate

Does ENCOURAGING the extractor to weave a rehydrated link into its `answer`
(for affordance cases: "the reviews are here: <url>") improve caller usefulness
over the structured `try_url` field alone?

**Genuinely uncertain — why it needs an eval, not a ship:**
- FOR: a self-contained prose answer is directly usable; the caller doesn't have
  to cross-reference a separate `try_url` array to act.
- AGAINST: the caller is an AI AGENT. A structured `try_url: [{url, reason}]` is
  arguably MORE machine-actionable than a URL buried in prose. Inline may be
  redundant noise on top of try_url.
- NEUTRALITY (ADR-0012): an inline link must READ as relaying an affordance
  ("reviews are on this linked page"), never as a2web recommending/selecting.

## Eval design (A/B, run when not token-constrained)

- Corpus: the `affordance` class (hepsiburada-product-reviews, amazon-…,
  github-repo-issues, contact-page-channels).
- Arm A (current): answer = prose only; link in `try_url`.
- Arm B: prompt permits the model to reference a `{{n}}` handle in the answer
  when the answer's completion depends on a linked page; server rehydrates.
- Judge axis: caller actionability — can an agent act on the answer alone? Plus
  the existing quality/neutrality/no-fabrication criteria. Watch for: link
  duplicated in answer AND try_url (noise?), neutrality violations.

Prompt change for Arm B is small (allow answer-embedded handles); the server
seam already rehydrates (shipped above). NOT built until the A/B judges it a win.

---

## A/B RESULT (2026-07-11, deepseek-v4-flash via OpenRouter, temp 0, 2 real pages)

Controlled: real page HTML → local extraction → digest → extractor twice, only
the prompt arm varies. Scratch harness (regenerable), not committed.

**Case 1 — github.com/astral-sh/ruff, "what open issues?"** (content on a separate page):
- Arm A: "page doesn't list issues... 1,700+ on the Issues page" — URL only in try_url.
- Arm B: "...tracked on the GitHub Issues page: <real url>" — URL inline in answer
  (via {{n}} → rehydrated) AND in try_url. Self-contained. Neutral. Correct.

**Case 2 — pypi.org/project/httpx, "docs and source?"**:
- Arm A ALREADY put raw URLs in the answer (python-httpx.org, github.com/encode/httpx),
  try_url=0. Arm B same.

### Findings (sharper than the yes/no hypothesis)

1. Inline answer-links are useful AND already happen unprompted (Case 2 Arm A).
2. **Raw URLs in the answer bypass the closed set.** The digest/handle validation
   only covers `try_url`. A raw URL the model writes into `answer` prose is NOT
   rehydrated/validated — a latent hallucination vector `try_url` does not have.
   Case 2's URLs were correct (famous lib) but nothing guaranteed it.
3. Arm B is the SAFER channel: it routes inline links through {{n}} handles →
   shipped `rehydrate_text` validates them (Case 1). It CONVERTS the existing
   raw-URL-in-answer behavior into a closed-set one — when the model complies
   (Case 2 it still wrote raw URLs).

### Verdict / what we built (2026-07-11)

Hypothesis holds — inline answer-links are valuable. Resolution (design **D14**,
`EXTRACT_ROUTER_V1` v4):

- **BUILT (a) + the safety rule as ONE prompt clause** ("LINKS IN THE ANSWER ·
  HARD RULE"): the model MAY weave a `{{n}}` handle inline in the answer for a
  linked-page affordance (validated via rehydration), AND the ONLY URLs allowed
  anywhere in output are `{{n}}` handles or URLs literally in the page content —
  never from the model's own knowledge, never pattern-guessed. If the link isn't
  on the page, say so (ADR-0009), don't invent it.
- **REJECTED post-hoc strip (the earlier "(b)")** — too blunt: the digest is
  built from `<a href>`, so stripping "answer URLs not in the digest set" would
  also kill grounded page-TEXT URLs (the pypi case). Governing principle
  (user, 2026-07-11): **as long as the link was on the page, it's fine.** The
  prompt HARD RULE forbids the ungrounded class at the source without endangering
  the grounded one.
- **Deferred:** provenance-flagging answer URLs (verified/unverified on the wire)
  — only if the model ignores the HARD RULE in practice; eval will tell.

Confirmation A/B against v4 (does the model obey the HARD RULE, esp. the pypi
memory-URL case?) not yet re-run — token budget.

---

## v4 CONFIRMATION (2026-07-11, deepseek-v4-flash, same 2 pages)

Ran the shipped v4 prompt with a per-URL provenance check (grounded via
anchor-handle / grounded via page-text / UNGROUNDED-memory).

**First pass found a BUG (now fixed):** `.format()` on `tail_template` collapsed
the `{{n}}` marker instructions to `{n}` (single brace), so the model wrote
`{64}` / `{11}` inline — which `rehydrate_text` (matches `{{n}}`) missed → the
handle LEAKED into the answer un-rehydrated. `try_url` was unaffected (JSON
integer handle). Fix: marker refs in source written `{{{{n}}}}` so `.format()`
emits the literal `{{n}}` matching the digest (JSON examples keep `{{ }}`).

**After the fix — clean:**
- github "open issues?": answer carries the REAL issues URL inline (rehydrated
  handle); `try_url` grounded:anchor. Self-contained + validated.
- pypi "docs/source?": all answer URLs `grounded:anchor` — the doc/source links
  now come from the page's real anchors, NOT the model's memory (contrast the
  pre-HARD-RULE run, which wrote `python-httpx.org` from training). The HARD RULE
  (design D14) demonstrably shifted the model off memory-URLs onto grounded ones.

**Verdict: v4 works.** Inline answer-links land as real, grounded, closed-set
URLs; memory-URLs suppressed. Two nits (cosmetic, not blocking): the model
sometimes prints `label (url)` redundancy; provenance false-positives on trailing
punctuation are a scratch-checker artifact, not a real ungrounding. `make bench`
across the full `affordance` corpus is the next fidelity step when budget allows.
