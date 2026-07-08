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
# two-axis (structural_form + genre) router payload with optional obstacle +
# discovery hints. `cache_prefix_template` is byte-identical to
# `EXTRACT_CACHEABLE_V1.cache_prefix_template` — load-bearing for the v0.19
# cache-prefix invariant. The schema lives entirely in `tail_template` so the
# cache prefix stays byte-stable across all `(content, ask, request_routing,
# request_next_links)` combinations for a given `content`.
#
# Prompt shape locked from `eval/spikes/surface_eval_v2.py` (pre-impl
# validation eval). Findings: `eval/findings_2026-05-25-router-shape-pre-impl.md`.
#
# The "answer" field in the response IS the answer to the user's question —
# same as `EXTRACT_CACHEABLE_V1`'s output, just wrapped in a JSON envelope
# alongside the router-shape block. The extractor parses out `answer` and
# the rest into `RouterPayload`.
EXTRACT_ROUTER_V1 = PromptTemplate(
    name="extract_router_v1",
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
        " - Never produce or reproduce exact song lyrics.\n"
        "\n"
        "You ALSO act as a routing helper: classify the page on two orthogonal "
        "axes and emit drilldown hints. The classification helps a downstream "
        "agent decide whether THIS page answers their question, or whether to "
        "ask again here (same URL) or follow a different URL. Output strict "
        "JSON only.",
    ),
    # MUST stay byte-identical to EXTRACT_CACHEABLE_V1.cache_prefix_template —
    # any change here breaks the v0.19 cache-prefix invariant.
    cache_prefix_template="Web page content:\n{content}\n",
    tail_template=(
        "\nQuestion: {ask}\n"
        "\n"
        "Return a single JSON object with these fields:\n"
        "\n"
        "  answer (required, string) — your concise answer to the question. If the\n"
        "    question asks for an enumeration (top N, list, etc.) put the list IN the\n"
        "    answer as compact markdown.\n"
        "    SELECTION questions (which / best / compare / all, over a SET of items —\n"
        "    products, contact channels, menu items): do NOT assert YOUR OWN 'best'. You have\n"
        "    no criteria; the criteria belong to the caller. Instead PRESENT the option space\n"
        "    and stay exhaustive (declining to crown is NOT license to under-deliver — give\n"
        "    the full set, not a thin pick). You MAY offer a criterion-disclosed lead — name\n"
        "    the criterion and frame it as ONE lens ('by rating, X leads; by price, Y') — but\n"
        "    never an unqualified 'X is best'. RELAY any preference the PAGE ITSELF states,\n"
        "    attributed to the source ('the site marks WhatsApp as the preferred contact'),\n"
        "    never as your own verdict. Single-fact questions (a phone number, a date) are\n"
        "    unaffected — answer directly and leanly.\n"
        "\n"
        "  structural_form (required, ONE of):\n"
        "    article    — long-form prose (essay, post, news story)\n"
        "    thread     — discussion-shaped page (HN item, reddit thread, lobste, blog with comments)\n"
        "    listing    — feed of items (catalog, index, search results, RSS-like)\n"
        "    reference  — encyclopedia / docs / spec / glossary / API reference\n"
        "    tutorial   — how-to / walkthrough / lesson\n"
        "    changelog  — release notes / version history\n"
        "    code       — source file, gist, raw code paste\n"
        "    product    — single product / package / project landing page\n"
        "    media      — primarily image / video / audio with thin text\n"
        "    other      — does not fit above\n"
        "\n"
        "  shape (required, ONE of) — the data SHAPE of the answer-bearing content:\n"
        "    prose       — paragraphs\n"
        "    records     — repeated rows of the same kind (each with a few fields)\n"
        "    key-value   — labeled fields (metadata, infobox, definition list)\n"
        "    code        — code blocks dominate\n"
        "    table       — actual tabular data\n"
        "    discussion  — thread with author + body pairs, often nested; both content AND replies\n"
        "    mixed       — multiple shapes co-exist with no dominant one\n"
        "\n"
        "  genre (optional, ONE of) — what the page is ABOUT. OMIT the key when no value\n"
        "  clearly applies:\n"
        "    news | encyclopedia | spec | paper | personal | official | community\n"
        "\n"
        "  obstacle (optional, ONE of) — page-level failure mode. OMIT on healthy pages:\n"
        "    paywalled | blocked | empty | error\n"
        "\n"
        "  ask_here (optional, list of strings) — same-URL follow-up questions a downstream\n"
        "  agent might ask. Emit ONLY questions whose answer requires READING THE BODY of\n"
        "  this page — never obvious-from-title or boilerplate questions. Context decides\n"
        "  count: 3 good, 5 great, more if rich. When shape=discussion, lean higher (5+\n"
        "  acceptable) — thread pages support useful follow-ups about positions, dissent,\n"
        "  consensus, top voices. OMIT the key entirely when no good follow-up exists.\n"
        "\n"
        "  try_url (optional, list of {{url, reason}}) — different-URL drilldowns. `url` MUST\n"
        "  appear verbatim in the page content above. `reason` MUST be question-conditioned\n"
        "  (WHY this URL likely has what the current page is missing) and ≤120 chars. Context\n"
        "  decides count: 3 good, 5 great, up to 10 on rich pages, OMIT on simple pages.\n"
        "\n"
        "  item_total_seen (optional, int) — ONLY when structural_form=listing: the TOTAL number\n"
        "  of items/results the PAGE ITSELF advertises (e.g. a '1123 results' / '1,123 ürün' /\n"
        "  '32,346 comments' count), in ANY language. Report the number you can READ on the page\n"
        "  even when only a subset of rows is shown. OMIT when the page states no total.\n"
        "\n"
        "  refinement_axes (optional, list of {{dimension, how}}) — when structural_form=listing and\n"
        "  the question is a SELECTION (which/best/compare), surface the CRITERIA this option set can\n"
        "  be judged on — the dimensions a 'best' would need, since you supply none yourself. This\n"
        "  applies to ANY such listing, complete or truncated. Propose DIMENSIONS the agent can\n"
        '  re-query or judge on: e.g. {{"dimension": "price floor", "how": "add a minimum price to skip\n'
        '  the cheapest tier"}}, {{"dimension": "sort order", "how": "sort by rating instead of price"}},\n'
        '  {{"dimension": "brand", "how": "narrow to one brand to compare"}}, and dimensions visible in\n'
        "  the item NAMES themselves (power/wattage, class, capacity, connector type). NEVER name a\n"
        "  specific value or item from the rows shown (no 'buy brand X', no 'the cheapest are best') —\n"
        "  name the AXIS, not a value. Consider the page's own URL and its query parameters (visible in\n"
        "  the content) — an existing sort or filter is itself an axis the agent can change. Context\n"
        "  decides count: 2-4 axes. OMIT on non-listings and non-selection questions.\n"
        "\n"
        "Envelope discipline: when a field is empty / null / does-not-apply, OMIT the key\n"
        "ENTIRELY. Do not emit `null` or `[]` — absence carries the meaning.\n"
        "\n"
        "Example (healthy article, complete answer, no drilldowns warranted):\n"
        "  {{\n"
        '    "answer": "<concise answer>",\n'
        '    "structural_form": "article",\n'
        '    "shape": "prose",\n'
        '    "genre": "encyclopedia"\n'
        "  }}\n"
        "\n"
        "Example (discussion page with follow-ups):\n"
        "  {{\n"
        '    "answer": "<concise answer>",\n'
        '    "structural_form": "thread",\n'
        '    "shape": "discussion",\n'
        '    "genre": "community",\n'
        '    "ask_here": ["<q1>", "<q2>", "<q3>", "<q4>", "<q5>"]\n'
        "  }}\n"
        "\n"
        "Example (paywalled obstacle):\n"
        "  {{\n"
        '    "answer": "<2-3 sentence statement naming the obstacle>",\n'
        '    "structural_form": "article",\n'
        '    "shape": "prose",\n'
        '    "obstacle": "paywalled",\n'
        '    "try_url": [{{"url": "<archive-url>", "reason": "archive snapshot"}}]\n'
        "  }}\n"
        "\n"
        "Example (truncated, price-sorted product listing):\n"
        "  {{\n"
        '    "answer": "<concise answer over the rows shown>",\n'
        '    "structural_form": "listing",\n'
        '    "shape": "records",\n'
        '    "item_total_seen": 1123,\n'
        '    "refinement_axes": [\n'
        '      {{"dimension": "price floor", "how": "add a minimum price to skip the cheapest tier"}},\n'
        '      {{"dimension": "sort order", "how": "sort by rating instead of price"}},\n'
        '      {{"dimension": "brand", "how": "narrow to one brand to compare like-for-like"}}\n'
        "    ]\n"
        "  }}\n"
    ),
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
