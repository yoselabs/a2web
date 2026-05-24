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


@dataclass(frozen=True, slots=True)
class PromptParts:
    """The rendered prompt split for cache-marker placement.

    `system` and `cache_prefix` together form the byte-stable prefix that
    a provider's caching layer keys on. `tail` carries the per-call
    variable portion (typically `{ask}`).

    Non-cacheable templates render with `cache_prefix=""` — providers then
    concatenate `cache_prefix + tail` and behave as before.
    """

    system: str
    cache_prefix: str
    tail: str


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

# v0.20 — affordances-aware template. Extends `EXTRACT_CACHEABLE_V1` by
# adding a two-axis (page_kind_confidence + content_value) affordances request
# to the *tail* (per-call portion). The `cache_prefix_template` is byte-
# identical to `EXTRACT_CACHEABLE_V1.cache_prefix_template` — load-bearing for
# the v0.19 cache-prefix invariant. The schema example lives entirely in
# `tail_template` so the cache prefix stays byte-stable across all `(content,
# ask, include_affordances, request_next_links)` combinations for a given
# `content`.
#
# Prompt shape locked from `eval/spikes/affordances_v5_two_axes.py` (V_CTX_V3,
# the winning iteration from the 4-spike calibration loop). Findings:
# `eval/findings_2026-05-24-affordances-v5-two-axes.md`.
#
# The "extracted_answer" field in the response IS the answer to the user's
# question — same as `EXTRACT_CACHEABLE_V1`'s output, just wrapped in a JSON
# envelope alongside the affordances block. The extractor parses out
# `extracted_answer` for the answer field and the rest for `AffordancesPayload`.
EXTRACT_WITH_AFFORDANCES_V1 = PromptTemplate(
    name="extract_with_affordances_v1",
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
        "You ALSO classify the page TYPE and emit affordances about what else "
        "the page offers. Two orthogonal signals matter:\n"
        "  - page_kind_confidence — how sure you are about the LABEL\n"
        "  - content_value — how useful the extracted content is downstream\n"
        "These are independent. A 404 page is HIGH confidence (it is clearly a "
        "404) but the content_value is implicitly NONE — for obstacle pages you "
        "OMIT content_value entirely (its absence carries the meaning). Be honest "
        "about uncertainty. Output strict JSON only.",
    ),
    # MUST stay byte-identical to EXTRACT_CACHEABLE_V1.cache_prefix_template —
    # any change here breaks the v0.19 cache-prefix invariant.
    cache_prefix_template="Web page content:\n{content}\n",
    tail_template=(
        "\nQuestion: {ask}\n"
        "\n"
        "STEP 1 — Classify the page. Pick the ONE best `page_kind` from this closed set:\n"
        "\n"
        "  Content kinds:\n"
        "    listing | thread | reference | api-reference | tutorial | article-short |\n"
        "    article-long | changelog | code-snippet | source-file | readme | qa | spec |\n"
        "    filing | news-article | blog-post | product-page | video-page | json-feed |\n"
        "    marketing | encyclopedia | package-page | pdf-stub | spa\n"
        "  Obstacle kinds (page exists but has no usable body):\n"
        "    paywalled    — clear paywall, partial content visible\n"
        "    error        — 404, 500, 'not found', broken page\n"
        "    empty        — nav + footer only, no real body\n"
        "    blocked      — captcha, bot wall, cloudflare interstitial\n"
        "  Catch-all:\n"
        "    other        — page exists but does not fit any label above\n"
        "\n"
        "STEP 2 — `page_kind_confidence` (epistemic uncertainty about the LABEL).\n"
        "\n"
        "  HARD RULE: if your chosen page_kind appears in any of these confusable\n"
        "  clusters, you MUST set confidence to `low` or `medium` — never `high`.\n"
        "  Claiming `high` while picking from a cluster is a contract violation:\n"
        "\n"
        "    Cluster A (academic / short articles):\n"
        "      article-short, reference, pdf-stub, article-long\n"
        "    Cluster B (project landing pages):\n"
        "      readme, package-page, marketing, product-page\n"
        "    Cluster C (status / dashboard / monitoring):\n"
        "      status, product-page\n"
        "    Cluster D (versioned release lists):\n"
        "      changelog, listing\n"
        "    Cluster E (structured feed of items):\n"
        "      listing, json-feed\n"
        "    Cluster F (long-form web content):\n"
        "      blog-post, news-article, article-long\n"
        "    Cluster G (commerce / listing of products):\n"
        "      listing, product-page, package-page\n"
        "\n"
        "  Decision rule inside a cluster:\n"
        "    low    — you considered 2+ labels from the same cluster and the\n"
        "             distinction is genuinely ambiguous\n"
        "    medium — one label is clearly stronger but a sibling is defensible\n"
        "\n"
        "  Use `high` ONLY when:\n"
        "    - the page_kind is NOT in any cluster above, AND\n"
        "    - structural signals are unambiguous\n"
        "\n"
        "STEP 3 — `content_value` (how useful the extracted content is downstream).\n"
        "\n"
        "  Emit this field ONLY when page_kind is a content kind.\n"
        "  For obstacle kinds (error / paywalled / blocked / empty), OMIT it.\n"
        "\n"
        "  high   — substantial body content (> 2000 chars), on-topic\n"
        "  medium — usable body present but partial, noisy, or only partially on-topic\n"
        "  low    — body very thin, mostly chrome/nav/footer, off-topic, or truncated\n"
        "\n"
        "STEP 4 — Affordances. For content kinds, emit shapes + follow_up_questions\n"
        "tuned to the kind. For obstacle kinds, OMIT both fields entirely.\n"
        "\n"
        "Use closed shape vocabulary:\n"
        "  list | timeline | key-value | table | code | comments | citations | comparison\n"
        "\n"
        "Respond with strict JSON. Include only the fields that apply.\n"
        "\n"
        "  Content page response:\n"
        "  {{\n"
        '    "extracted_answer": "<concise answer to the question above>",\n'
        '    "page_kind": "<content kind>",\n'
        '    "page_kind_confidence": "<low|medium|high>",\n'
        '    "content_value": "<low|medium|high>",\n'
        '    "reasoning": "<one short sentence justifying kind + confidence + value>",\n'
        '    "shapes": [{{"label": "...", "where": "...", "size": "..."}}],\n'
        '    "follow_up_questions": ["<3-5 specific questions>"]\n'
        "  }}\n"
        "\n"
        "  Obstacle page response (no content_value, no shapes, no follow_ups):\n"
        "  {{\n"
        '    "extracted_answer": "<2-3 sentence statement naming the obstacle>",\n'
        '    "page_kind": "<obstacle kind>",\n'
        '    "page_kind_confidence": "<low|medium|high>",\n'
        '    "reasoning": "<one short sentence>"\n'
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
    "EXTRACT_WITH_AFFORDANCES_V1",
    "JUDGE_V1",
    "TERSE_V1",
    "WEBFETCH_DEFAULT_V1",
    "PromptParts",
    "PromptTemplate",
]
