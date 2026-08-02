"""Spike — does schema-shaped extraction make a2web say LESS?

The question, from the user, reading back `I0269`:

    "one concern I have — such a shape, will it make us give less info — bc
     that is what bad. In general more information is better than less."

`eval/findings_2026-08-02-schema-shaped-extraction.md` argues on evidence that
the risk is real but SPLITS: classifying the entity is a task structure helps,
while letting a schema shape the `answer` is a task structure hurts. This spike
exists to MEASURE that split rather than assert it, and specifically to make the
losing arm visible instead of hypothetical.

**Three arms, same pages, same questions, same provider, same content bytes.**

  A  control        `EXTRACT_ROUTER_V1` verbatim — what ships today.
  B  additive       + `entity_type` + `entity_fields`, placed AFTER `answer`.
                    The `answer` clause is untouched, byte for byte.
  C  entity-first   the same two fields placed BEFORE `answer`, with `answer`
                    told not to repeat what `entity_fields` carries.
                    This is the NAIVE reading of I0269 §2 ("shape its output
                    around a schema, lead with the type discriminator").

**Arm C is the point.** Without it there is no evidence that schema-shaping
WOULD have cost anything — only an assertion that it might. C is not a proposal;
it is the control for the claim.

**Primary metric — answer recall.** A blind judge builds ONE fact inventory per
page from the page itself (never from any arm's answer), then marks which of
those facts each arm's `answer` relays. Recall is comparable across arms because
the inventory is fixed before any arm is scored, and the arms are shuffled and
relabelled X/Y/Z so the judge cannot know which is which.

Reading the result:
  * B ≈ A  → additive entity extraction is free. The design in the findings doc
             holds and the proposal can proceed.
  * B < A  → even additive schema fields cost relay completeness. That kills the
             additive design too, not just C.
  * C < A  → the naive schema-shaping would have cost real content. Records WHY
             the proposal is additive-only.
  * C ≈ A  → the satisficing prior is wrong on this corpus. Say so; do not
             quietly keep the conclusion the prior implied.

**Secondary metrics.** `also_here` count is the satisficing tell — if B suppresses
the same-page index relative to A, the entity block is absorbing the index rather
than adding to it, which is the `also_here` under-fire of 2026-07-11 repeating
one layer up. Also: `entity_type` populated rate, extra-field survival (properties
outside schema.org's common vocabulary — the `couponCode` case), answer length,
and completion tokens.

**Corpus.** Pages with a RICH BODY BEYOND their structured data, because that is
where dropping is visible. A schema-only page (Koçtaş, 1.6k chars) cannot show
the effect and would produce a falsely clean result — the same trap as the
`also_here` two-causes analysis, where an under-FETCH looked like an under-INDEX.
Narrow asks on rich pages are weighted deliberately: that configuration is where
satisficing showed up before.

**Scope limit, stated rather than hidden.** `other_pages` is NOT measured. It
depends on the link-digest suffix the orchestrator builds inside the answer
phase, which this spike does not reconstruct; a number produced without it would
be an artifact of the harness. `answer` and `also_here` are digest-independent
and carry the question being asked.

**Cost posture (ADR-0016).** Subscription only: resolves `claude-code-sdk` by
default and wraps it in the shelf cost guard, so a metered pair raises
`CostViolation` BEFORE any spend. If no subscription backend resolves this exits
loudly rather than falling through to metered billing.

**Variance is the failure mode of a spike like this**, so it is designed against
rather than hoped away. Each arm is sampled `REPS` times per page, and the
headline statistic is the **paired delta** (B−A and C−A within the same page and
the same scoring round), not a difference of grand means. Pairing removes
page difficulty — by far the largest source of spread here — and a per-page
delta table is printed so one outlier page cannot masquerade as an effect.

Live network + LLM quota. Not part of `make check`. Run:

    uv run python eval/spikes/entity_schema_v1.py [N_PAGES] [REPS]
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from anyllm import ProviderName, with_cost_guard

from a2web.components import build_components
from a2web.fetcher import fetch
from a2web.llm_resource import select_provider
from a2web.packages.llm_extract.prompts import _ROUTER_SCHEMA_DOC, EXTRACT_ROUTER_V1, PromptTemplate
from a2web.settings import AppSettings

_OUT = Path(__file__).resolve().parent / "entity_schema_v1_summary.json"

#: Subscription-only default (ADR-0016). Override only with another
#: subscription backend; a metered pair is rejected by the cost guard anyway.
_PROVIDER_ENV = "A2WEB_BENCH_PROVIDER"
_DEFAULT_PROVIDER = "claude-code-sdk"

#: Same cap the production extractor applies, so all three arms see identical
#: content bytes and a recall difference cannot come from a truncation difference.
_CONTENT_CAP = 60_000
_JUDGE_CONTENT_CAP = 40_000
_MAX_FACTS = 30

# --------------------------------------------------------------------------
# Corpus — rich body beyond the structured data. See the module docstring on
# why a schema-only page would produce a falsely clean result.
# --------------------------------------------------------------------------

#: `(slug, url, ask, why_this_page)`. `why` is carried into the summary so a
#: later reader can tell whether a null result came from a corpus that could
#: not have shown the effect.
CASES: list[tuple[str, str, str, str]] = [
    (
        "wikipedia-rust-narrow",
        "https://en.wikipedia.org/wiki/Rust_(programming_language)",
        "Who created Rust and in what year did it first appear?",
        "narrow ask on a 42k-char body — the exact configuration where `also_here` under-fired",
    ),
    (
        "wikipedia-transformer-narrow",
        "https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)",
        "What is multi-head attention?",
        "narrow ask, rich reference page, no meaningful JSON-LD to lean on",
    ),
    (
        "arxiv-abstract",
        "https://arxiv.org/abs/2401.05566",
        "What is the paper's title and its main contribution in one sentence?",
        "ScholarlyArticle entity + prose abstract the schema does not carry",
    ),
    (
        "pypi-httpx",
        "https://pypi.org/project/httpx/",
        "What is httpx, what is its current version, and what Python versions does it support?",
        "SoftwareApplication entity + a long README body beneath it",
    ),
    (
        "python-contact",
        "https://www.python.org/about/help/",
        "How can I contact them — is there an email or a specific channel?",
        "Organization/ContactPoint — the entity IS the answer, so C should look strongest here",
    ),
    (
        "github-ruff",
        "https://github.com/astral-sh/ruff",
        "What is ruff and what are its main features?",
        "SoftwareSourceCode + a long README; heavy nav chrome to resist",
    ),
    (
        "hn-item",
        "https://news.ycombinator.com/item?id=9224",
        "What is this Hacker News discussion about, and what is the main disagreement?",
        "a thread has NO clean entity — stresses whether entity_type degrades gracefully",
    ),
    (
        "hepsiburada-product",
        "https://www.hepsiburada.com/wilkinson-sword-wilkinson-swrod-hydro-5-ultimate-tirasmakinesi-1-adet-yedek-baslik-p-HBV00000UWKQ2",
        "What is this product, its price and currency, and is it in stock?",
        "commerce Product with real body — the `discountPrice`/extra-field survival case",
    ),
]

# --------------------------------------------------------------------------
# The entity block — identical text in B and C, only its POSITION differs.
# --------------------------------------------------------------------------

#: Deliberately mirrors the two rules the findings doc derives: the vocabulary
#: is SUGGESTED not enforced (presence validated, value never), and the official
#: schema is a floor rather than a ceiling (extra properties are the point).
_ENTITY_BLOCK = """
  entity_type (required, string) — the schema.org @type of the PRIMARY THING this
    page is about: "Product", "Person", "Article", "ScholarlyArticle", "JobPosting",
    "Recipe", "SoftwareApplication", "Organization", "Event", ... Use the schema.org
    vocabulary when one fits. If nothing fits, write the most accurate name you can
    rather than forcing a wrong one — this field is NOT validated against a list.
    If the page is a listing of many things, give the type of the ITEMS.
    NEVER omit this field; write "Thing" if the page is genuinely about no one thing.

  entity_fields (required, object of string -> string) — that entity's properties AS
    STATED ON THE PAGE, flat. Use schema.org property names where one fits (name,
    price, priceCurrency, brand, author, datePublished, version, ...) and the SITE'S
    OWN name for anything schema.org does not cover (discountPrice, couponCode,
    whatever this page invented this quarter). NEVER drop a property because the
    official vocabulary has no slot for it — the extra properties are the point.
    Empty object {} when the page is about no particular thing.
"""

#: Arm C's extra directive. This is the naive I0269 §2 reading made concrete:
#: lead with the type discriminator, then the schema, and let `answer` become the
#: leftover. Written to be a FAIR version of that idea, not a strawman — it is
#: what someone implementing the note in good faith would write.
_ENTITY_FIRST_DIRECTIVE = """
FIELD ORDER MATTERS: decide `entity_type` FIRST, then fill `entity_fields` with
the page's facts about that entity, and only then write `answer`. Because
`entity_fields` already carries the page's structured facts, keep `answer` to a
brief 1-3 sentence response to the question and do NOT repeat there what
`entity_fields` already states.
"""

#: Anchors for the string surgery. Both are asserted at import time — a prompt
#: edit that moves them must fail loudly here rather than silently produce an
#: arm that is secretly the control (the "guard that checks nothing" failure).
_ANCHOR_OBSTACLE = "\n  obstacle (optional, ONE of)"
_ANCHOR_ANSWER = "\n  answer (required, string)"


def _build_arms() -> dict[str, PromptTemplate]:
    """Build the three arms by surgery on the SHIPPED schema doc.

    Deriving B and C from `_ROUTER_SCHEMA_DOC` rather than copying it means the
    arms cannot drift from production between this spike and the next one — a
    copied prompt is a fixture that encodes today's assumption and goes stale
    silently.
    """
    doc = _ROUTER_SCHEMA_DOC
    if _ANCHOR_OBSTACLE not in doc or _ANCHOR_ANSWER not in doc:
        raise SystemExit(
            "entity_schema_v1: the anchors this spike splices on are gone from "
            "_ROUTER_SCHEMA_DOC. The prompt moved; re-derive the arms rather than "
            "running a spike whose B/C are silently identical to A."
        )

    # B — entity block AFTER `answer`/`structural_form`/`shape`, before `obstacle`.
    doc_b = doc.replace(_ANCHOR_OBSTACLE, _ENTITY_BLOCK + _ANCHOR_OBSTACLE, 1)

    # C — entity block BEFORE `answer`, plus the ordering directive.
    doc_c = doc.replace(_ANCHOR_ANSWER, _ENTITY_BLOCK + _ANCHOR_ANSWER, 1) + _ENTITY_FIRST_DIRECTIVE

    if doc_b == doc or doc_c == doc:  # pragma: no cover - spike self-check
        raise SystemExit("entity_schema_v1: an arm came out identical to the control")

    base_system = EXTRACT_ROUTER_V1.system[:-1]  # every element except the schema doc

    def _arm(name: str, schema_doc: str) -> PromptTemplate:
        return PromptTemplate(
            name=name,
            version=EXTRACT_ROUTER_V1.version,
            system=(*base_system, schema_doc),
            cache_prefix_template=EXTRACT_ROUTER_V1.cache_prefix_template,
            tail_template=EXTRACT_ROUTER_V1.tail_template,
        )

    return {"A": EXTRACT_ROUTER_V1, "B": _arm("entity_additive", doc_b), "C": _arm("entity_first", doc_c)}


# --------------------------------------------------------------------------
# Tolerant JSON read — spike-local
# --------------------------------------------------------------------------

#: `packages/llm_extract/wobble` is the production funnel and this is deliberately
#: NOT it: wobble applies per-field recovery POLICY, which would silently repair
#: exactly the degradation this spike is trying to observe. A spike that heals its
#: own signal measures the healer. Fence-stripping only, then a plain parse.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _loads(text: str) -> dict[str, Any] | None:
    stripped = _FENCE.sub("", text or "").strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


# --------------------------------------------------------------------------
# Judge
# --------------------------------------------------------------------------

_INVENTORY_SYSTEM = (
    "You build fact inventories from web page content. You never see or consider any candidate answer. Output strict JSON only."
)

_INVENTORY_USER = """Below is the text of one web page, and a question a user asked about it.

List the atomic, checkable facts STATED ON THIS PAGE that a reader who asked this
question would want to receive. Include both facts that answer the question
directly AND substantive facts the page carries that such a reader would want
alongside it. Exclude navigation, boilerplate, cookie notices, and anything not
actually stated on the page.

Each fact must be ONE assertion, self-contained, and checkable against the page.
At most {max_facts}. Order them most-relevant-first.

PAGE CONTENT:
{content}

QUESTION: {ask}

Strict JSON only, no prose, no markdown fence:
{{"facts": ["<fact>", "..."]}}"""

_SCORING_SYSTEM = (
    "You score candidate answers against a fixed fact list. You do not know which "
    "system produced which answer and must not speculate. Output strict JSON only."
)

_SCORING_USER = """A user asked this question about a web page:

QUESTION: {ask}

Here is a numbered list of facts the page states:

{facts}

Below are three candidate answers, labelled X, Y and Z, in no meaningful order.
For each label, list the NUMBERS of the facts that the answer actually conveys.
A fact counts as conveyed only if the answer states it or clearly implies it —
not if the answer merely gestures at the topic. Judge only what is written.

--- X ---
{x}

--- Y ---
{y}

--- Z ---
{z}

Strict JSON only, no prose, no markdown fence:
{{"X": [<numbers>], "Y": [<numbers>], "Z": [<numbers>]}}"""


#: A coarse schema.org core vocabulary, used ONLY to count how many properties
#: fall OUTSIDE it (the `couponCode` survival signal). It gates nothing — which
#: is the whole point of the finding it measures, and the reason `_RECIPE_LABELS`
#: was demoted to a label table on 2026-08-01.
_SCHEMA_ORG_COMMON = frozenset(
    {
        "name",
        "description",
        "url",
        "image",
        "author",
        "creator",
        "datepublished",
        "datemodified",
        "headline",
        "price",
        "pricecurrency",
        "brand",
        "sku",
        "gtin",
        "availability",
        "aggregaterating",
        "ratingvalue",
        "reviewcount",
        "offers",
        "version",
        "softwareversion",
        "programminglanguage",
        "license",
        "publisher",
        "identifier",
        "keywords",
        "abstract",
        "email",
        "telephone",
        "address",
        "contactpoint",
        "startdate",
        "enddate",
        "location",
        "inlanguage",
        "genre",
    },
)


async def _complete(provider: Any, *, system: str, user: str, model: str, max_tokens: int) -> tuple[str, int]:
    response = await provider.complete(
        system=system,
        user=user,
        model=model,
        max_tokens=max_tokens,
        thinking_disabled=True,
    )
    text = getattr(response, "text", "") or ""
    tokens = int(getattr(response, "completion_tokens", 0) or 0)
    return text, tokens


async def _run_arm(provider: Any, template: PromptTemplate, *, content: str, ask: str, model: str) -> dict[str, Any]:
    parts = template.render(content=content, ask=ask)
    user = parts.cache_prefix + parts.tail if parts.cache_prefix else parts.tail
    started = time.monotonic()
    text, tokens = await _complete(provider, system=parts.system, user=user, model=model, max_tokens=4096)
    payload = _loads(text)
    if payload is None:
        return {"parse_failed": True, "raw_len": len(text), "ms": round((time.monotonic() - started) * 1000)}

    fields = payload.get("entity_fields")
    fields = fields if isinstance(fields, dict) else {}
    extra = [k for k in fields if str(k).lower() not in _SCHEMA_ORG_COMMON]
    answer = payload.get("answer")
    also = payload.get("also_here")
    return {
        "parse_failed": False,
        "answer": answer if isinstance(answer, str) else "",
        "answer_chars": len(answer) if isinstance(answer, str) else 0,
        "also_here": len(also) if isinstance(also, list) else 0,
        "structural_form": payload.get("structural_form"),
        "entity_type": payload.get("entity_type"),
        "entity_field_count": len(fields),
        "entity_extra_fields": extra,
        "completion_tokens": tokens,
        "ms": round((time.monotonic() - started) * 1000),
    }


async def _inventory(provider: Any, *, content: str, ask: str, model: str) -> list[str]:
    text, _ = await _complete(
        provider,
        system=_INVENTORY_SYSTEM,
        user=_INVENTORY_USER.format(content=content[:_JUDGE_CONTENT_CAP], ask=ask, max_facts=_MAX_FACTS),
        model=model,
        max_tokens=4096,
    )
    payload = _loads(text) or {}
    facts = payload.get("facts")
    return [str(f) for f in facts][:_MAX_FACTS] if isinstance(facts, list) else []


async def _score(
    provider: Any,
    *,
    ask: str,
    facts: list[str],
    answers: dict[str, str],
    model: str,
) -> dict[str, list[int]]:
    """Blind-score the three arms against a fixed fact list.

    Labels are shuffled per page so a judge with a positional or alphabetical
    bias cannot systematically favour one arm.
    """
    labels = ["X", "Y", "Z"]
    arms = list(answers)
    random.shuffle(arms)
    mapping = dict(zip(labels, arms, strict=True))
    numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts))
    text, _ = await _complete(
        provider,
        system=_SCORING_SYSTEM,
        user=_SCORING_USER.format(
            ask=ask,
            facts=numbered,
            x=answers[mapping["X"]] or "(no answer)",
            y=answers[mapping["Y"]] or "(no answer)",
            z=answers[mapping["Z"]] or "(no answer)",
        ),
        model=model,
        max_tokens=2048,
    )
    payload = _loads(text) or {}
    out: dict[str, list[int]] = {}
    for label, arm in mapping.items():
        hits = payload.get(label)
        out[arm] = sorted({int(n) for n in hits if isinstance(n, int) and 1 <= n <= len(facts)}) if isinstance(hits, list) else []
    return out


# --------------------------------------------------------------------------


def _paired(rounds: list[dict[str, float]], lhs: str, rhs: str) -> dict[str, Any]:
    """Paired delta `lhs - rhs` over rounds that scored BOTH arms.

    Paired, not a difference of means: page difficulty dominates the spread, and
    it is shared within a round. An unpaired comparison on this corpus would need
    far more samples to see the same effect — and a null result from it would be
    indistinguishable from "we did not sample enough", which is the failure this
    spike is trying not to have.
    """
    deltas = [r[lhs] - r[rhs] for r in rounds if lhs in r and rhs in r]
    if not deltas:
        return {"n": 0}
    wins = sum(1 for d in deltas if d > 0)
    losses = sum(1 for d in deltas if d < 0)
    return {
        "n": len(deltas),
        "mean": round(statistics.fmean(deltas), 4),
        "stdev": round(statistics.stdev(deltas), 4) if len(deltas) > 1 else 0.0,
        "wins": wins,
        "ties": len(deltas) - wins - losses,
        "losses": losses,
    }


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(CASES)
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    cases = CASES[:limit]
    arms = _build_arms()

    settings = AppSettings()
    raw = os.environ.get(_PROVIDER_ENV, "").strip().lower() or _DEFAULT_PROVIDER
    try:
        override = ProviderName(raw)
    except ValueError:
        raise SystemExit(f"entity_schema_v1: unknown provider id {raw!r}") from None
    provider = select_provider(settings, override=override)
    if provider is None:
        # Fail loud rather than fall through to metered billing (ADR-0016).
        raise SystemExit(f"entity_schema_v1: no LLM provider available (tried: {raw})")
    provider = with_cost_guard(provider)
    model = settings.llm_model

    parts = build_components(settings=settings)
    rows: list[dict[str, Any]] = []
    try:
        for i, (slug, url, ask, why) in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {slug}", flush=True)
            row: dict[str, Any] = {"slug": slug, "url": url, "ask": ask, "why": why}
            try:
                response = await fetch(
                    url,
                    state=await parts.state(),
                    llm_extractor=parts.llm_extractor,
                    browser_backend=parts.browser_backend,
                    browser_robust_backend=parts.browser_robust_backend,
                    cookie_jar=parts.cookie_jar,
                )
                content = (response.content_md or "")[:_CONTENT_CAP]
                row["status"] = response.status
                row["content_chars"] = len(content)
                if len(content) < 500:
                    # A page that did not retrieve cannot discriminate the arms;
                    # recording it as a null result would be a measurement of the
                    # fetch, reported as a measurement of the prompt.
                    row["skipped"] = "content too thin to discriminate arms"
                    rows.append(row)
                    print(f"      -> SKIP ({len(content)} chars)", flush=True)
                    continue

                # One inventory per page, built BEFORE any arm is scored and
                # never shown an answer — so every rep and every arm is scored
                # against the same fixed target.
                facts = await _inventory(provider, content=content, ask=ask, model=model)
                row["fact_count"] = len(facts)
                row["facts"] = facts
                if not facts:
                    row["skipped"] = "judge produced no fact inventory"
                    rows.append(row)
                    print("      -> SKIP (no inventory)", flush=True)
                    continue

                reps_out: list[dict[str, Any]] = []
                for rep in range(reps):
                    results = {}
                    for arm, template in arms.items():
                        results[arm] = await _run_arm(provider, template, content=content, ask=ask, model=model)
                    covered = await _score(
                        provider,
                        ask=ask,
                        facts=facts,
                        answers={a: r.get("answer", "") for a, r in results.items()},
                        model=model,
                    )
                    recall = {a: round(len(v) / len(facts), 3) for a, v in covered.items()}
                    reps_out.append({"arms": results, "covered": covered, "recall": recall})
                    print(
                        f"      rep{rep + 1} recall={recall} "
                        f"also_here={ {a: results[a].get('also_here') for a in arms} } "
                        f"entity={ {a: results[a].get('entity_type') for a in arms} }",
                        flush=True,
                    )
                row["reps"] = reps_out
            except Exception as exc:  # a spike reports failures, it does not hide them
                row["error"] = f"{type(exc).__name__}: {exc}"
                print(f"      -> ERROR {row['error']}", flush=True)
            rows.append(row)
            # Checkpoint after every page. A full sweep is ~100 live calls over
            # tens of minutes; writing only at the end means one late failure
            # discards every page that already succeeded, and the rerun spends
            # the quota again to recover data that was already in hand.
            _OUT.write_text(json.dumps({"partial": True, "rows": rows}, indent=2))
    finally:
        await parts.aclose()

    scored = [r for r in rows if r.get("reps")]
    all_rounds = [rep["recall"] for r in scored for rep in r["reps"]]
    all_arm_runs = [rep["arms"] for r in scored for rep in r["reps"]]

    def _recall_mean(arm: str) -> float | None:
        vals = [rd[arm] for rd in all_rounds if arm in rd]
        return round(statistics.fmean(vals), 3) if vals else None

    def _arm_mean(arm: str, field: str) -> float | None:
        vals = [run[arm][field] for run in all_arm_runs if not (run.get(arm) or {}).get("parse_failed") and field in (run.get(arm) or {})]
        return round(statistics.fmean(vals), 2) if vals else None

    def _per_page_recall(r: dict[str, Any]) -> dict[str, float]:
        return {a: round(statistics.fmean([rep["recall"][a] for rep in r["reps"] if a in rep["recall"]]), 3) for a in arms}

    per_page = {r["slug"]: _per_page_recall(r) for r in scored}

    summary: dict[str, Any] = {
        "provider": str(getattr(provider, "name", raw)),
        "model": model,
        "reps": reps,
        "n_pages": len(rows),
        "n_scored_pages": len(scored),
        "n_rounds": len(all_rounds),
        # PRIMARY — paired, because page difficulty dominates the spread.
        "paired_recall_delta": {
            "B-A": _paired(all_rounds, "B", "A"),
            "C-A": _paired(all_rounds, "C", "A"),
            "C-B": _paired(all_rounds, "C", "B"),
        },
        "recall_mean": {a: _recall_mean(a) for a in arms},
        "recall_per_page": per_page,
        "also_here_mean": {a: _arm_mean(a, "also_here") for a in arms},
        "answer_chars_mean": {a: _arm_mean(a, "answer_chars") for a in arms},
        "completion_tokens_mean": {a: _arm_mean(a, "completion_tokens") for a in arms},
        "entity_populated": {a: sum(1 for run in all_arm_runs if (run.get(a) or {}).get("entity_type")) for a in arms},
        "entity_types_seen": {
            a: sorted({str((run.get(a) or {}).get("entity_type")) for run in all_arm_runs if (run.get(a) or {}).get("entity_type")})
            for a in arms
        },
        "extra_fields_total": {a: sum(len((run.get(a) or {}).get("entity_extra_fields") or []) for run in all_arm_runs) for a in arms},
        "parse_failures": {a: sum(1 for run in all_arm_runs if (run.get(a) or {}).get("parse_failed")) for a in arms},
        "rows": rows,
    }
    _OUT.write_text(json.dumps(summary, indent=2))

    print("\n=== summary ===")
    print(f"  provider/model     : {summary['provider']} / {model}")
    print(f"  pages / rounds     : {len(scored)}/{len(rows)} pages, {len(all_rounds)} scored rounds (reps={reps})")
    print("\n  PAIRED recall delta (within page+round) <- PRIMARY")
    for pair, st in summary["paired_recall_delta"].items():
        if st.get("n"):
            print(f"    {pair}: mean={st['mean']:+.4f} sd={st['stdev']:.4f} W/T/L={st['wins']}/{st['ties']}/{st['losses']}  (n={st['n']})")
    print(f"\n  recall mean        : {summary['recall_mean']}")
    print(f"  also_here mean     : {summary['also_here_mean']}   <- satisficing tell")
    print(f"  answer chars mean  : {summary['answer_chars_mean']}")
    print(f"  completion tokens  : {summary['completion_tokens_mean']}")
    print(f"  entity_type filled : {summary['entity_populated']} of {len(all_rounds)} rounds")
    print(f"  entity types seen  : {summary['entity_types_seen']}")
    print(f"  extra fields kept  : {summary['extra_fields_total']}")
    print(f"  parse failures     : {summary['parse_failures']}")
    print("\n  per-page recall (mean over reps):")
    for slug, rec in per_page.items():
        d_b = rec.get("B", 0) - rec.get("A", 0)
        d_c = rec.get("C", 0) - rec.get("A", 0)
        print(f"    {slug:34s} A={rec.get('A'):.2f} B={rec.get('B'):.2f} C={rec.get('C'):.2f}   B-A={d_b:+.2f} C-A={d_c:+.2f}")
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    asyncio.run(main())
