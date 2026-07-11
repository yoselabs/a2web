"""Frozen, versioned prompt templates for the a2web.llm Extractor + Judge.

Templates carry a name + version. `WEBFETCH_DEFAULT_V1` is byte-for-byte
identical to Claude Code's WebFetch user-prompt template (`Rb9` in the
Claude Code binary; see research note
`~/Documents/Knowledge/Researches/123-claude-code-webfetch-internals/`).

Adding a new template = a new module-level constant. The eval suite picks
templates up automatically via reflection so adding one doesn't require a
runner change.

v0.19 — cache-aware rendering: `PromptTemplate.render(content, ask)`
returns a `PromptParts(system, cache_prefix, tail)` triple. Templates that
populate `cache_prefix_template` (a `{content}` format string) opt in to
the cache-friendly shape: providers place `cache_control` markers between
`cache_prefix` and `tail` (Anthropic) or rely on byte-stable concatenation
(Claude Code SDK / OpenAI auto-cache). Templates that don't opt in render
the whole user message into `tail` — degenerate shape, behavior unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# PromptParts moved to the shelf (anyllm) with the provider contract — a2web's
# Extractor/Judge templates render into it and the anyllm adapters consume it.
# Re-exported here so the package's own consumers keep importing it from
# `llm_extract.prompts` unchanged.
from anyllm import PromptParts


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A frozen prompt template — name, version, system, user template.

    Two render modes:

    1. **Legacy / flat**: `user_template` contains `{content}` and `{ask}`
       placeholders. `render()` formats the whole string and packs it into
       `PromptParts.tail` with `cache_prefix=""`.

    2. **Cacheable**: `cache_prefix_template` (contains `{content}`) and
       `tail_template` (contains `{ask}`) are both non-empty. `render()`
       formats each part separately; the static portions live in
       `system` and `cache_prefix`, the variable portion in `tail`.

    `system` is a tuple of strings (joined with `\\n\\n` at render time).
    Empty tuple is the WebFetch-parity shape per research/123.
    """

    name: str
    version: int
    system: tuple[str, ...] = field(default_factory=tuple)
    user_template: str = ""
    cache_prefix_template: str = ""
    tail_template: str = ""

    def render(self, *, content: str, ask: str) -> PromptParts:
        """Render the template into a PromptParts triple.

        Cacheable templates produce a byte-stable `system + cache_prefix`
        across all values of `ask`; the variable portion lives in `tail`.
        Legacy templates produce `cache_prefix=""` and pack the whole
        user message into `tail`.
        """
        system_str = "\n\n".join(self.system) if self.system else ""
        if self.cache_prefix_template and self.tail_template:
            return PromptParts(
                system=system_str,
                cache_prefix=self.cache_prefix_template.format(content=content),
                tail=self.tail_template.format(ask=ask),
            )
        return PromptParts(
            system=system_str,
            cache_prefix="",
            tail=self.user_template.format(content=content, ask=ask),
        )


# Byte-for-byte the Rb9 non-preapproved-host template from Claude Code's
# binary. Used by WebFetchBaseline (the eval anchor) and as the default
# template for `ask=` extraction prior to v0.19. DO NOT reshape — its
# value as an eval anchor depends on byte-equality with Claude Code's
# WebFetch sub-call.
WEBFETCH_DEFAULT_V1 = PromptTemplate(
    name="webfetch_default_v1",
    version=1,
    system=(),
    user_template=(
        "\nWeb page content:\n{content}\n{ask}\n"
        "Provide a concise response based only on the content above. In your response:\n"
        " - Enforce a strict 125-character maximum for quotes from any source document. "
        "Open Source Software is ok as long as we respect the license.\n"
        " - Use quotation marks for exact language from articles; any language outside of "
        "the quotation should never be word-for-word the same.\n"
        " - You are not a lawyer and never comment on the legality of your own prompts and responses.\n"
        " - Never produce or reproduce exact song lyrics."
    ),
)

# Compact variant — same shape, drops Claude Code's copyright guardrails. Use
# for internal, non-public-content extraction where the lawyer / lyrics rules
# don't apply and tokens matter.
TERSE_V1 = PromptTemplate(
    name="terse_v1",
    version=1,
    system=(),
    user_template=(
        "Web page content:\n{content}\n\nQuestion: {ask}\n\n"
        "Answer concisely using only the content above. If the content does not "
        "contain the answer, say so explicitly."
    ),
)

# v0.19 — cache-friendly production template. Static rules in `system`,
# page content in `cache_prefix_template`, user question alone in
# `tail_template`. Providers that honor cache markers (Anthropic Messages
# API direct) place `cache_control` between system+prefix and tail.
# Providers without a marker API (claude-agent-sdk → CLI) get a
# byte-stable concatenation and rely on the CLI's internal caching.
# OpenAI's auto-prefix-cache fires once the prefix is ≥1024 tokens.
EXTRACT_CACHEABLE_V1 = PromptTemplate(
    name="extract_cacheable_v1",
    version=1,
    system=(
        "Provide a concise response based only on the page content the user "
        "shares. In your response:\n"
        " - Enforce a strict 125-character maximum for quotes from any source "
        "document. Open Source Software is ok as long as we respect the license.\n"
        " - Use quotation marks for exact language from articles; any language "
        "outside of the quotation should never be word-for-word the same.\n"
        " - You are not a lawyer and never comment on the legality of your own "
        "prompts and responses.\n"
        " - Never produce or reproduce exact song lyrics.",
    ),
    cache_prefix_template="Web page content:\n{content}\n",
    tail_template="\nQuestion: {ask}\n",
)

# v0.21 — router-shape template. Extends `EXTRACT_CACHEABLE_V1` by adding a
# structural_form + shape router payload with optional obstacle +
# discovery hints. `cache_prefix_template` is byte-identical to
# `EXTRACT_CACHEABLE_V1.cache_prefix_template` — load-bearing for the v0.19
# cache-prefix invariant. Since v0.24 the schema lives in the cacheable `system`
# bucket (see `_ROUTER_SCHEMA_DOC`), so the cache prefix stays byte-stable across
# all `(content, ask, request_routing, request_next_links)` combinations for a
# given `content`, and the static schema no longer rides the per-call `tail`.
#
# Prompt shape locked from `eval/spikes/surface_eval_v2.py` (pre-impl
# validation eval). Findings: `eval/findings_2026-05-25-router-shape-pre-impl.md`.
#
# v0.22 (ask-extraction-token-tuning) — bumped to version=2 in place (same
# `name`, so `template_name` cache/log keying stays stable while eval history
# can still tell pre/post-tuning runs apart): dropped `genre` (zero downstream
# consumer — see design D3), and added a token-efficiency + partial-signal
# honesty instruction to `system`. `cache_prefix_template` is untouched, so
# the v0.19 cache-prefix invariant is unaffected. Router-shape calls bypass
# the extraction cache entirely (`Extractor.extract` skips lookup when
# `request_routing=True`), so there is no cache-staleness concern either way.
#
# v0.23 (ask-response-contract-v2) — bumped to version=5 in place (same `name`).
# ADR-0015 (the withheld-body index): `ask_here` → `also_here`, emitted as terse
# QUERY strings (deletion rule: drop the verb frame + known entity; keep target
# noun + one operator) with a listing-orthogonality clause; `try_url` → a unified
# `other_pages` list carrying a per-item `kind` (structural | drilldown), folding
# the old drilldown-only shape and the handler-continuation family into one field.
# The ADR-0014 "LINKS · HARD RULE" clause + `{{{{n}}}}` double-brace discipline are
# preserved verbatim. `cache_prefix_template` untouched (v0.19 invariant holds).
#
# v0.24 (cache-router-shape-schema) — bumped to version=6 in place (same `name`).
# Pure relocation, zero wording change: the ~5.8k-char static schema + 4 worked
# examples moved OUT of `tail_template` (resent every call) INTO the cacheable
# `system` bucket (`_ROUTER_SCHEMA_DOC`). `tail_template` is now only the per-call
# `"\nQuestion: {ask}\n"`. Because `system` is emitted verbatim (never `.format()`d),
# the schema is single-braced there and `{{n}}` handle markers stay double-braced
# (no escaping) — the inverse of the old `{{{{n}}}}` tail discipline. Rendered
# aggregate content is unchanged; only the system/tail bucket split moved.
# `cache_prefix_template` untouched (v0.19 invariant holds).
#
# v0.25 (also-here-indexes-rich-pages) — bumped to version=7 in place (same `name`).
# Strengthened the `also_here` clause: "covered" now means relayed EVERYTHING the
# page holds, not merely answered the asked question. A narrow ask on a rich
# product/article/reference/thread almost never covers the page → index the
# unsurfaced sections instead of emitting `also_here=[]` (the koçtaş under-fire,
# eval/findings_2026-07-11-also-here-underfires.md). Listing carve-out + thin-page
# escape unchanged. `cache_prefix_template` untouched (v0.19 invariant holds).
#
# The "answer" field in the response IS the answer to the user's question —
# same as `EXTRACT_CACHEABLE_V1`'s output, just wrapped in a JSON envelope
# alongside the router-shape block. The extractor parses out `answer` and
# the rest into `RouterPayload`.
# v0.24 (cache-router-shape-schema): the router-shape JSON schema + 4 worked
# examples, relocated here from tail_template into the cacheable `system` bucket.
# Single-braced (system is emitted verbatim — NOT .format()'d — so `{` / `}` are
# literal and `{{n}}` handle markers stay double-braced here, no escaping needed,
# unlike the old tail_template's `{{{{n}}}}` discipline).
_ROUTER_SCHEMA_DOC = """Return a single JSON object with these fields:

  answer (required, string) — your concise answer to the question. If the
    question asks for an enumeration (top N, list, etc.) put the list IN the
    answer as compact markdown.
    SELECTION questions (which / best / compare / all, over a SET of items —
    products, contact channels, menu items): do NOT assert YOUR OWN 'best'. You have
    no criteria; the criteria belong to the caller. Instead PRESENT the option space
    and stay exhaustive (declining to crown is NOT license to under-deliver — give
    the full set, not a thin pick). You MAY offer a criterion-disclosed lead — name
    the criterion and frame it as ONE lens ('by rating, X leads; by price, Y') — but
    never an unqualified 'X is best'. RELAY any preference the PAGE ITSELF states,
    attributed to the source ('the site marks WhatsApp as the preferred contact'),
    never as your own verdict. Single-fact questions (a phone number, a date) are
    unaffected — answer directly and leanly.
    LINKS IN THE ANSWER: when the answer's completion depends on a LINKED page (the
    asked-for content is not here but reachable via a {{n}} link below), you MAY weave
    that {{n}} handle inline in the answer ('reviews are on a separate page: {{1}}') —
    the server replaces it with the real URL. Relay it as an affordance, never a
    recommendation. HARD RULE: the ONLY URLs allowed anywhere in your output are {{n}}
    handles from the page-links list, or URLs that appear LITERALLY in the page content
    above. NEVER write a URL from your own knowledge, and NEVER guess/construct one by
    pattern (e.g. appending '/reviews'). If the link you need is not on the page, SAY
    it was not found — do not invent it.
    EVIDENCE-SCOPED ABSENCE: when the asked-for content is not in what you were given,
    scope the absence to THIS page and THIS evidence ('not stated on this page', 'no
    such link among the page's links') — NEVER assert it does not exist at all ('this
    product has no reviews', 'there is no contact info'). You saw one page, not the
    whole site; a genre-level nonexistence claim is a false negative exactly when the
    content lives on a page you did not fetch.

  structural_form (required, ONE of):
    article    — long-form prose (essay, post, news story)
    thread     — discussion-shaped page (HN item, reddit thread, lobste, blog with comments)
    listing    — feed of items (catalog, index, search results, RSS-like)
    reference  — encyclopedia / docs / spec / glossary / API reference
    tutorial   — how-to / walkthrough / lesson
    changelog  — release notes / version history
    code       — source file, gist, raw code paste
    product    — single product / package / project landing page
    media      — primarily image / video / audio with thin text
    other      — does not fit above

  shape (required, ONE of) — the data SHAPE of the answer-bearing content:
    prose       — paragraphs
    records     — repeated rows of the same kind (each with a few fields)
    key-value   — labeled fields (metadata, infobox, definition list)
    code        — code blocks dominate
    table       — actual tabular data
    discussion  — thread with author + body pairs, often nested; both content AND replies
    mixed       — multiple shapes co-exist with no dominant one

  obstacle (optional, ONE of) — page-level failure mode. OMIT on healthy pages:
    paywalled | blocked | empty | error

  also_here (optional, list of query strings) — the same-page INDEX: pointers to
  SPECIFIC content that IS on this page but did NOT reach your `answer` (a specs
  table, a pricing tier, a section you summarized past). A downstream agent never
  sees the page body — this is your index of what you withheld, one cheap same-URL
  re-query away, NOT a curiosity list. Write each as a terse QUERY, not a question:
  DROP the verb frame ('does it have', 'are there') and the already-known page
  entity; KEEP the target noun(s) plus at most ONE operator — `,` (list) · `vs`
  (contrast) · `/` (alternatives). CAPS at most one load-bearing token (the decider).
  Keep a trailing `?` ONLY for a DECIDE item (judge / which-wins); a FIND (retrieve)
  item takes none. SPLIT an `and`-joined item into two. e.g. `return policy`,
  `battery vs mains life`, `setup steps ONLY in working reviews`. ORTHOGONALITY: on
  structural_form=listing DEFER to options / refinement_axes and stay sparse; NEVER
  restate a heading, an option row, or a refinement axis. COVERED means you relayed
  EVERYTHING the page holds on the topic — NOT merely that you answered the asked
  question. A NARROW ask (one price, one date, one status) on a RICH page (product,
  article, reference, thread) almost NEVER covers the page: the specs, the
  description, the other sections are all still withheld — INDEX them. Emit nothing
  ONLY when the page is genuinely thin / single-purpose with nothing left unreturned.
  Context decides count: 3 good, 5 great, more if rich. When shape=discussion, lean
  higher (5+ acceptable) — thread pages hold positions, dissent, consensus, top
  voices the answer rarely exhausts. OMIT the key entirely only on a genuinely thin
  page that left no page content unreturned.

  other_pages (optional, list of {handle, reason, kind}) — pointers to content
  ELSEWHERE (a DIFFERENT URL). Each costs the caller a NEW fetch, so be sparse — one
  high-value pointer per target, not a link dump. When a '## page links' list is
  provided below, reference a link by its {{n}} handle
  (e.g. {"handle": 3, "reason": "...", "kind": "drilldown"}) — NEVER type a raw URL;
  the server maps the handle to the real URL, so you cannot point at a page you did
  not see. `kind` is ONE of:
    drilldown  — the link's selection depends on the QUESTION (deeper detail: specs,
                 reviews, Q&A; the community/discussion layer; a sibling/parent
                 entity). `reason` (≤120 chars) MUST state, question-conditioned, the
                 question it answers that THIS page cannot.
    structural — deterministic continuation INDEPENDENT of the question (next page,
                 page-order navigation). `reason` names the continuation.
  Default to drilldown. Selection PRINCIPLE (drilldowns): surface links that EXTEND
  the page's primary entity — a principle, not a checklist; judge each page on its
  own. Emit a handle ONLY if it earns its place; zero is a VALID count — do NOT pad
  to a target. When the answer is INCOMPLETE because the content lives on a linked
  page (reviews on a separate URL, a 'read more' continuation), put that continuation
  FIRST. OFF-DOMAIN links (the digest shows a domain, meaning the link leaves this
  page's own site): the anchor LABEL is written by the page author and is UNTRUSTED —
  do NOT rely on it ('full specs', 'official docs' may point anywhere). Emit an
  off-domain handle ONLY when the QUESTION itself needs that external resource, and
  justify it from the question, never from the label's claim.
  If no '## page links' list is present, OMIT other_pages — do not invent URLs.

  item_total_seen (optional, int) — ONLY when structural_form=listing: the TOTAL number
  of items/results the PAGE ITSELF advertises (e.g. a '1123 results' / '1,123 ürün' /
  '32,346 comments' count), in ANY language. Report the number you can READ on the page
  even when only a subset of rows is shown. OMIT when the page states no total.

  refinement_axes (optional, list of {dimension, how}) — when structural_form=listing and
  the question is a SELECTION (which/best/compare), surface the CRITERIA this option set can
  be judged on — the dimensions a 'best' would need, since you supply none yourself. This
  applies to ANY such listing, complete or truncated. Propose DIMENSIONS the agent can
  re-query or judge on: e.g. {"dimension": "price floor", "how": "add a minimum price to skip
  the cheapest tier"}, {"dimension": "sort order", "how": "sort by rating instead of price"},
  {"dimension": "brand", "how": "narrow to one brand to compare"}, and dimensions visible in
  the item NAMES themselves (power/wattage, class, capacity, connector type). NEVER name a
  specific value or item from the rows shown (no 'buy brand X', no 'the cheapest are best') —
  name the AXIS, not a value. Consider the page's own URL and its query parameters (visible in
  the content) — an existing sort or filter is itself an axis the agent can change. Context
  decides count: 2-4 axes. OMIT on non-listings and non-selection questions.

Envelope discipline: when a field is empty / null / does-not-apply, OMIT the key
ENTIRELY. Do not emit `null` or `[]` — absence carries the meaning.

Example (healthy article, complete answer, no drilldowns warranted):
  {
    "answer": "<concise answer>",
    "structural_form": "article",
    "shape": "prose"
  }

Example (discussion page with follow-ups):
  {
    "answer": "<concise answer>",
    "structural_form": "thread",
    "shape": "discussion",
    "also_here": ["<target, target>", "<a vs b>", "<qualifier target>", "<target>", "<DECIDE which?>"]
  }

Example (paywalled obstacle):
  {
    "answer": "<2-3 sentence statement naming the obstacle>",
    "structural_form": "article",
    "shape": "prose",
    "obstacle": "paywalled"
  }

Example (product page; reviews live on a separate linked page — continuation FIRST):
  {
    "answer": "<what the product page DOES state; note reviews are not on this page>",
    "structural_form": "product",
    "shape": "key-value",
    "other_pages": [{"handle": 4, "reason": "customer reviews live on this linked page", "kind": "drilldown"}]
  }

Example (truncated, price-sorted product listing):
  {
    "answer": "<concise answer over the rows shown>",
    "structural_form": "listing",
    "shape": "records",
    "item_total_seen": 1123,
    "refinement_axes": [
      {"dimension": "price floor", "how": "add a minimum price to skip the cheapest tier"},
      {"dimension": "sort order", "how": "sort by rating instead of price"},
      {"dimension": "brand", "how": "narrow to one brand to compare like-for-like"}
    ]
  }
"""

EXTRACT_ROUTER_V1 = PromptTemplate(
    name="extract_router_v1",
    version=7,
    system=(
        "Provide a concise response based only on the page content the user "
        "shares. In your response:\n"
        " - Enforce a strict 125-character maximum for quotes from any source "
        "document. Open Source Software is ok as long as we respect the license.\n"
        " - Use quotation marks for exact language from articles; any language "
        "outside of the quotation should never be word-for-word the same.\n"
        " - You are not a lawyer and never comment on the legality of your own "
        "prompts and responses.\n"
        " - Never produce or reproduce exact song lyrics.\n"
        " - Be aggressively terse in your own prose framing — minimize filler and\n"
        "   hedging language — but NEVER drop a factual value, identifier, name,\n"
        "   number, or unit present in the source content to save space. Prefer\n"
        "   ASCII punctuation (straight quotes, hyphens, `...`) over Unicode\n"
        "   look-alikes (curly quotes, em dashes, ellipsis character) in your own\n"
        "   prose, where meaning is unaffected; this does not apply to verbatim\n"
        "   quoted material, which stays governed by the 125-character quote rule\n"
        "   above.\n"
        " - When the content mentions the topic asked about but lacks the specific\n"
        '   level of detail requested, report what IS present (e.g. "the page lists\n'
        '   X as a category but gives no further detail") — do NOT assert the page\n'
        "   does not address the topic at all. Only say the content does not address\n"
        "   the topic when the topic is genuinely absent, not merely under-detailed.\n"
        "\n"
        "You ALSO act as a routing helper: classify the page on two orthogonal "
        "axes and emit drilldown hints. The classification helps a downstream "
        "agent decide whether THIS page answers their question, or whether to "
        "ask again here (same URL) or follow a different URL. Output strict "
        "JSON only.",
        _ROUTER_SCHEMA_DOC,
    ),
    # MUST stay byte-identical to EXTRACT_CACHEABLE_V1.cache_prefix_template —
    # any change here breaks the v0.19 cache-prefix invariant.
    cache_prefix_template="Web page content:\n{content}\n",
    tail_template="\nQuestion: {ask}\n",
)

# Judge template — produces strict-JSON verdict over an answer + criteria.
# Consumed by `Judge` in judge.py. Designed for low variance — terse, JSON-
# only, blind to system identity.
JUDGE_V1 = PromptTemplate(
    name="judge_v1",
    version=1,
    system=(),
    user_template=(
        "You are a strict, blind judge evaluating an answer to a question about "
        "a web page. You do NOT know which system produced this answer. Score it "
        "against the criteria below. Reward concise correctness, penalize "
        "fabrication. A 'fetch failed / no content' answer correctly admitting "
        "failure scores low on substantive criteria but should have `reached=False`.\n\n"
        "QUESTION ASKED: {ask}\n\n"
        "CRITERIA (each scored 0-5, where 0=absent, 3=partial, 5=fully satisfied):\n{content}\n\n"
        "ANSWER TO JUDGE:\n{answer}\n\n"
        "Respond with STRICT JSON ONLY, no prose, no markdown fence:\n"
        '{{"scores":[<int per criterion>], "overall":<int 0-5>, '
        '"reached":<bool>, "reasoning":"<one sentence>"}}'
    ),
)


__all__ = [
    "EXTRACT_CACHEABLE_V1",
    "EXTRACT_ROUTER_V1",
    "JUDGE_V1",
    "TERSE_V1",
    "WEBFETCH_DEFAULT_V1",
    "PromptParts",
    "PromptTemplate",
]
