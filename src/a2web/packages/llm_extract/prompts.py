"""Frozen, versioned prompt templates for the a2web.llm Extractor + Judge.

Templates carry a name + version. `WEBFETCH_DEFAULT_V1` is byte-for-byte
identical to Claude Code's WebFetch user-prompt template (`Rb9` in the
Claude Code binary; see research note
`~/Documents/Knowledge/Researches/123-claude-code-webfetch-internals/`).

Adding a new template = a new module-level constant. The eval suite picks
templates up automatically via reflection so adding one doesn't require a
runner change.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """A frozen prompt template — name, version, system, user template.

    `user_template` SHALL contain `{content}` and `{ask}` placeholders, in
    that order. The Extractor formats with `.format(content=..., ask=...)`.

    `system` is a list of strings (or empty list). Empty list is the
    WebFetch-parity shape per research/123 — Claude Code sends no system
    content to its Haiku sub-call.
    """

    name: str
    version: int
    system: tuple[str, ...] = field(default_factory=tuple)
    user_template: str = ""


# Byte-for-byte the Rb9 non-preapproved-host template from Claude Code's
# binary. Used by WebFetchBaseline (the eval anchor) and as the default
# template for `ask=` extraction in v0.4.
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
    "JUDGE_V1",
    "TERSE_V1",
    "WEBFETCH_DEFAULT_V1",
    "PromptTemplate",
]
