"""Spike — does claude-agent-sdk auto-cache behind the scenes?

Probe published 2026-05-23 confirmed the SDK source has zero `cache_control`
references — we hypothesised the Claude CLI binary applies caching internally
given a byte-stable prefix. This script tests that experimentally by running
the production Extractor four times against the same `EXTRACT_CACHEABLE_V1`
template and inspecting `ResultMessage.usage` for cache_read / cache_creation
tokens.

Run:
    uv run python eval/spikes/claude_code_cache_probe.py

Requires the `claude` CLI installed and logged-in (no API key needed; the
provider piggybacks the OS session).

Output: a short markdown table to stdout. Findings should be pasted into
`eval/findings_<date>-claude-code-cache-probe.md`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from a2web.packages.llm_extract import (
    EXTRACT_CACHEABLE_V1,
    Extractor,
    ModelSpec,
)
from a2web.packages.llm_extract.providers.claude_code import ClaudeCodeProvider


# A ~5 KB page — comfortably above any minimum-token caching threshold and
# representative of a real wiki/article extraction.
_PAGE_A = """# The Lighthouse Keeper of Tristan da Cunha

Tristan da Cunha is the most remote inhabited archipelago in the world, sitting
some 2,400 kilometres west of Cape Town in the South Atlantic Ocean. Of its
several islands, only the eponymous main island is permanently populated, with
roughly 245 residents who share a small set of family names — Glass, Repetto,
Swain, Hagan, Green, Lavarello, Rogers — descended from the original 19th-century
settlers.

## Geography

The main island is a single composite volcano roughly 12 km across, rising
abruptly from the sea to a 2,062 m peak. The settlement of Edinburgh of the
Seven Seas occupies a narrow strip of flat ground on the north coast; the rest
of the island is sheer cliff and lava field. Three smaller islands — Inaccessible,
Nightingale, and Gough — lie nearby but are uninhabited except for a South
African weather station on Gough.

The climate is cool-temperate maritime, with mean annual temperature around
14°C and high rainfall year-round. Winds reach gale force frequently; the
landing beach at Edinburgh is workable on roughly 60 days per year.

## Economy

The fishery for Tristan rock lobster (*Jasus tristani*) accounts for the
overwhelming share of cash income; a single annual quota is negotiated with the
South African concession holder. Postage stamps issued by the islanders also
generate hard currency at a level disproportionate to the tiny population —
philatelists have collected Tristan stamps since the 1950s. Wool, potatoes, and
fish are produced for local consumption.

## Communication

Mail arrives via a roughly nine-day passage from Cape Town aboard the fishery
vessel or the South African research ship SA Agulhas II, which calls at the
island roughly every 60 days during the southern summer. A satellite link
provides limited internet bandwidth shared across the settlement; routine
medical consultations with specialists in Cape Town occur via this link.

## Governance

The archipelago is a British Overseas Territory administered from St Helena,
nearly 2,000 km to the north. A locally-elected Island Council advises the
Administrator (a UK civil servant on a typical three-year posting). Tristanians
hold British Overseas Territories citizenship.

## Notable events

In October 1961, an eruption of the previously-quiescent main volcano forced
the evacuation of the entire population to the UK via Cape Town. The
islanders lived in temporary accommodation in Calshot, Hampshire for nearly two
years before voting overwhelmingly to return; most of the population was back
on Tristan by the end of 1963.

In 2008 a fire destroyed the island's fish processing factory, cutting off the
main cash income for nearly two years. The factory was rebuilt with UK
development assistance and was operational again by 2010.
"""

# A different page — used to confirm the cache misses when the prefix changes.
_PAGE_B = """# Coffee Cultivation in the Western Highlands of Guatemala

The departments of Huehuetenango, San Marcos, and Quetzaltenango together
account for the majority of Guatemala's specialty arabica output. Altitudes
between 1,500 and 2,000 metres, volcanic soils, and a sharp dry season produce
beans favoured by third-wave roasters in North America and Europe.

## Varietals

Bourbon and Caturra remain dominant on smallholder farms, with Pacamara,
Geisha, and SL28 grown on a small minority of estates targeting the
competition-grade market. Anacafé (the national coffee institute) has promoted
rust-tolerant varieties since the 2012-13 leaf-rust crisis; the Marsellesa
and Centroamericano F1 hybrids are now widespread.

## Processing

Washed processing predominates: cherries are depulped within hours of picking,
fermented in tanks for 18-36 hours, then washed and dried on patios or raised
beds. Natural (dry-process) and honey-process lots are increasingly common at
specialty estates aiming for higher cup scores, though they carry meaningful
quality risk in the wet altitudes.

## Logistics

Beans move by truck from cooperative drying yards to dry mills in
Quetzaltenango or Guatemala City, where they are graded and bagged for export
through Puerto Quetzal on the Pacific or Puerto Barrios on the Atlantic.
"""


@dataclass(slots=True)
class _CallRecord:
    label: str
    page_label: str
    ask: str
    prompt_tokens: int
    cache_read: int
    cache_creation: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int


async def _one_call(extractor: Extractor, page: str, ask: str, page_label: str, label: str) -> _CallRecord:
    print(f"  → {label} ({page_label}, ask={ask[:40]!r}) ...", flush=True)
    t0 = time.perf_counter()
    result = await extractor.extract(content=page, ask=ask)
    elapsed = int((time.perf_counter() - t0) * 1000)

    cache_creation = 0
    cache_read = 0
    if result.raw is not None:
        # The Anthropic provider populates these via extract_token_counts; the
        # Claude Code path can also surface them through ResultMessage.usage
        # when present. We don't rely on the provider exposing them — we look
        # directly at the ProviderResponse path.
        pass

    return _CallRecord(
        label=label,
        page_label=page_label,
        ask=ask,
        prompt_tokens=result.prompt_tokens,
        cache_read=cache_read,
        cache_creation=cache_creation,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        latency_ms=elapsed,
    )


async def _run_via_provider_directly(model: str) -> list[_CallRecord]:
    """Bypass the Extractor's ExtractionResult shape — call the provider directly
    so we can read `cache_creation_input_tokens` / `cache_read_input_tokens`
    straight off `ResultMessage.usage`.
    """
    from a2web.packages.llm_extract.providers.base import extract_token_counts

    # We invoke the provider with a `parts` object built from the template so
    # the prompt shape matches production exactly.
    provider = ClaudeCodeProvider()

    plan: list[tuple[str, str, str]] = [
        ("call_1 (A / Q1) — establishes prefix", "A", "What is the population of Tristan da Cunha?"),
        ("call_2 (A / Q2) — same prefix, diff tail", "A", "What is the climate like?"),
        ("call_3 (B / Q2) — diff prefix, same tail", "B", "What is the climate like?"),
        ("call_4 (A / Q3) — back to A prefix, new tail", "A", "What happened in 1961?"),
        ("call_5 (A / Q1) — exact repeat of call_1", "A", "What is the population of Tristan da Cunha?"),
    ]

    records: list[_CallRecord] = []
    for label, page_label, ask in plan:
        page = _PAGE_A if page_label == "A" else _PAGE_B
        parts = EXTRACT_CACHEABLE_V1.render(content=page, ask=ask)

        print(f"  → {label}", flush=True)
        t0 = time.perf_counter()
        response = await provider.complete(
            system=EXTRACT_CACHEABLE_V1.system,
            user=parts.cache_prefix + parts.tail,
            model=model,
            max_tokens=512,
            thinking_disabled=True,
            parts=parts,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)

        # Pull cache_creation / cache_read straight off the raw ResultMessage
        # usage if the SDK surfaced it. ProviderResponse doesn't expose these
        # as named fields; we re-decompose from `raw` if present.
        cache_creation = 0
        cache_read = 0
        if response.raw is not None:
            usage = response.raw.get("usage")
            if usage is not None:
                _, _, cache_creation, cache_read = extract_token_counts(usage)
        # Fallback: try to read off the ProviderResponse's raw stash from the
        # claude_code path which stores ResultMessage.usage under "usage".
        records.append(
            _CallRecord(
                label=label,
                page_label=page_label,
                ask=ask,
                prompt_tokens=response.prompt_tokens,
                cache_read=cache_read,
                cache_creation=cache_creation,
                completion_tokens=response.completion_tokens,
                cost_usd=response.cost_usd,
                latency_ms=elapsed,
            )
        )
        # Small inter-call gap so the CLI flushes — but stay well within the
        # 5-minute prompt-cache TTL.
        await asyncio.sleep(0.2)

    return records


def _format_table(records: list[_CallRecord]) -> str:
    rows = [
        "| call | page | ask (truncated) | prompt_tok | cache_read | cache_create | latency_ms | cost_usd |",
        "|------|------|-----------------|-----------:|-----------:|-------------:|-----------:|---------:|",
    ]
    for r in records:
        rows.append(
            f"| {r.label.split(' ')[0]} | {r.page_label} | {r.ask[:40]} "
            f"| {r.prompt_tokens} | {r.cache_read} | {r.cache_creation} "
            f"| {r.latency_ms} | ${r.cost_usd:.5f} |"
        )
    return "\n".join(rows)


async def main() -> None:
    print("# Claude Code SDK cache-behaviour probe")
    print()
    print("Running 5 calls against the production EXTRACT_CACHEABLE_V1 template,")
    print("via ClaudeCodeProvider (piggybacks the `claude` CLI's OS session).")
    print()
    print("Hypothesis: same-page calls 2 and 4 should show non-zero cache_read")
    print("tokens; call 3 (different page) should show no cache_read on the prefix.")
    print("Call 5 is an exact repeat of call 1 — either ExtractionCache (our own")
    print("sqlite layer-2) intercepts it OR the CLI cache hits it.")
    print()

    model = "claude-haiku-4-5"
    records = await _run_via_provider_directly(model)
    print()
    print(_format_table(records))
    print()

    # Interpret.
    print("## Interpretation")
    print()
    same_page_calls = [r for r in records if r.page_label == "A"]
    if same_page_calls:
        first = same_page_calls[0]
        later = [r for r in same_page_calls[1:] if r.cache_read > 0]
        if later:
            print(f"- cache_read fired on {len(later)}/{len(same_page_calls) - 1} same-page follow-up calls.")
            print(f"  → Claude CLI IS applying cache behind the scenes.")
            saved = sum(r.cache_read for r in later)
            print(f"  → ~{saved} prompt tokens served from cache across the session.")
        else:
            print("- No cache_read tokens observed on any same-page follow-up.")
            print("  → Either the CLI is NOT auto-caching one-shot query() calls,")
            print("  → or `ResultMessage.usage` doesn't surface the cache counters.")
        del first
    diff_page = next((r for r in records if r.page_label == "B"), None)
    if diff_page and diff_page.cache_read == 0:
        print("- Different-page call (call_3) showed no cache_read → prefix-based cache key is working as expected.")


if __name__ == "__main__":
    asyncio.run(main())
