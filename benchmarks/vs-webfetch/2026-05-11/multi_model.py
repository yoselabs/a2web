"""Multi-model extraction winnow: stage 0 smoke → stage 1 ranked subset → stage 2 full.

Usage:
  uv run python benchmarks/vs-webfetch/2026-05-11/multi_model.py --stage 0
  uv run python benchmarks/vs-webfetch/2026-05-11/multi_model.py --stage 1
  uv run python benchmarks/vs-webfetch/2026-05-11/multi_model.py --stage 2

Each stage reads the previous stage's survivor list. State on disk:
  multi_model_state.json — current survivor list per stage
  multi_model_runs/<stage>/<model_safe>/<slug>.{ans.txt,meta.json,score.json}
  multi_model_summary_s{N}.json — flat per-row dump for that stage

Why three stages: blasting 13 models x 20 URLs = 260 calls + 260 judges.
Stage 0 (1 URL, no judge) kills 404s / broken models for ~$0.20.
Stage 1 (5 URLs, judged) ranks the rest, keep top 5-6 for ~$1-2.
Stage 2 (20 URLs, judged) is the final scoreboard on those ~5 survivors.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent
RUNS = HERE / "runs"
CORPUS = HERE / "corpus.yaml"
STATE = HERE / "multi_model_state.json"
MM_RUNS = HERE / "multi_model_runs"


# --- .env loader (no python-dotenv dep) ---------------------------------
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

from a2web.llm import Extractor, Judge, JudgeParseError, ModelSpec, PromptTemplate  # noqa: E402
from a2web.llm.errors import LLMNotAvailable  # noqa: E402
from a2web.llm.providers.anthropic import AnthropicProvider  # noqa: E402
from a2web.llm.providers.claude_code import ClaudeCodeProvider  # noqa: E402
from a2web.llm.providers.openrouter import OpenRouterProvider  # noqa: E402

# --- Model roster --------------------------------------------------------
# The user-supplied 13 names. Some are best guesses (model IDs evolve);
# Stage 0 will surface 404s. Add or correct names freely.
CANDIDATE_MODELS: list[str] = [
    # Initial roster (stage 0 already ran):
    "deepseek/deepseek-v3.2-exp",
    "deepseek/deepseek-chat-v3.1",
    "deepseek/deepseek-r1-0528",
    "qwen/qwen3-30b-a3b",
    "qwen/qwen3-235b-a22b",
    "qwen/qwen3-max",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "moonshotai/kimi-k2",
    "z-ai/glm-4.6",
    "minimax/minimax-m2",
    "tencent/hunyuan-large",
    "nvidia/nemotron-nano-9b-v2:free",
    # Expansion: production baselines (OpenAI / Llama / Mistral / Cohere /
    # Grok / Nova / Phi). Names use OpenRouter's current slugs as of 2026-05.
    "openai/gpt-4o-mini",
    "openai/gpt-4.1-mini",
    "anthropic/claude-haiku-4-5",
    "mistralai/mistral-large-2411",
    "meta-llama/llama-3.3-70b-instruct",
    "cohere/command-r-plus-08-2024",
    "x-ai/grok-2-1212",
    "amazon/nova-pro-v1",
    "microsoft/phi-4",
]

# Anchors: Haiku/Sonnet numbers already exist in phase 3/4 data — referenced
# in the final report, not re-run here (avoids needing ANTHROPIC_API_KEY).
ANCHOR_MODELS: dict[str, str] = {}

# --- Prompt: same as WebFetch parity template ----------------------------
from a2web.llm.prompts import WEBFETCH_DEFAULT_V1  # noqa: E402

# Judge always uses the same anchor: Sonnet via OS session (no extra spend).
JUDGE_MODEL = "claude-sonnet-4-6"

STAGE0_SLUG = "wikipedia-rust"  # one clean, well-defined URL
STAGE1_SLUGS = [
    "wikipedia-rust",     # A_clean
    "linear-marketing",   # B_gated (SPA / 404-prone)
    "vercel-blog",        # C_spa
    "github-issue",       # D_structured
    "non-english",        # E_edge
]
ALL_SLUGS_KEY = "_all"

# Pricing cap: cancel a model if it blows past this in tokens × ratio
MAX_OUTPUT_TOK = 1024


def _safe(name: str) -> str:
    """Filesystem-safe model name."""
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name)


def _build_provider_for(model: str) -> tuple[Any, str]:
    """Anchor models → AnthropicProvider; everything else → OpenRouter."""
    if model in ANCHOR_MODELS:
        return AnthropicProvider(), "anthropic"
    return OpenRouterProvider(), "openrouter"


async def _judge_provider() -> Judge:
    """Single judge instance — Sonnet via OS session (free for us)."""
    try:
        provider = ClaudeCodeProvider()
        return Judge(provider=provider, model=ModelSpec("claude-code", JUDGE_MODEL))
    except LLMNotAvailable:
        provider = AnthropicProvider()
        return Judge(provider=provider, model=ModelSpec("anthropic", JUDGE_MODEL))


async def _run_one(
    model: str,
    extractor: Extractor,
    slug: str,
    judge: Judge | None,
    entry: dict[str, Any],
    stage_dir: Path,
) -> dict[str, Any]:
    """Extract + (optionally) judge one (model, slug) cell."""
    out_dir = stage_dir / _safe(model)
    out_dir.mkdir(parents=True, exist_ok=True)
    task = entry["task"]
    criteria = entry["criteria"]
    # Use the cached a2web fetch payload from phase 1 as the {content}.
    payload_path = RUNS / slug / "a2web_C_content_only.json"
    if not payload_path.exists():
        payload_path = RUNS / slug / "a2web_A_full.json"
    content = ""
    if payload_path.exists():
        payload = json.loads(payload_path.read_text())
        content = payload.get("content_md") or ""
    if not content:
        return {
            "model": model,
            "slug": slug,
            "error": "no content_md in phase1 payload",
        }

    t0 = time.perf_counter()
    try:
        r = await extractor.extract(content=content, ask=task)
    except Exception as exc:
        return {
            "model": model,
            "slug": slug,
            "error": f"extract: {exc!r}",
        }
    wall = int((time.perf_counter() - t0) * 1000)

    (out_dir / f"{slug}.ans.txt").write_text(r.answer)
    meta = {
        "model": r.model,
        "template_name": r.template_name,
        "prompt_tokens": r.prompt_tokens,
        "completion_tokens": r.completion_tokens,
        "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms or wall,
        "cache_hit": r.cache_hit,
    }
    (out_dir / f"{slug}.meta.json").write_text(json.dumps(meta, indent=2))

    row: dict[str, Any] = {
        "model": model,
        "slug": slug,
        "class": entry.get("class", "?"),
        **meta,
        "answer_chars": len(r.answer),
        "empty": not r.answer.strip(),
    }

    if judge is not None and r.answer.strip():
        try:
            v = await judge.score(task=task, criteria=criteria, answer=r.answer)
            v_dict = asdict(v)
            (out_dir / f"{slug}.score.json").write_text(json.dumps(v_dict, indent=2))
            row["judge"] = {"overall": v.overall, "reached": v.reached}
        except JudgeParseError as exc:
            row["judge"] = {"error": str(exc)[:120]}
    elif judge is not None:
        row["judge"] = {"error": "empty answer"}

    return row


def _summarize(rows: list[dict[str, Any]], stage: int) -> dict[str, Any]:
    """Aggregate per-model: cells_ok, mean overall, mean cost, mean latency."""
    by_model: dict[str, dict[str, Any]] = {}
    for r in rows:
        m = r["model"]
        b = by_model.setdefault(
            m,
            {"cells_ok": 0, "errors": 0, "overall": [], "cost": 0.0, "latency": [], "empty": 0},
        )
        if "error" in r:
            b["errors"] += 1
            continue
        b["cells_ok"] += 1
        b["cost"] += float(r.get("cost_usd", 0) or 0)
        b["latency"].append(int(r.get("latency_ms", 0) or 0))
        if r.get("empty"):
            b["empty"] += 1
        j = r.get("judge", {})
        if isinstance(j, dict) and "overall" in j:
            b["overall"].append(int(j["overall"]))
    out: dict[str, Any] = {}
    for m, b in by_model.items():
        mean_overall = sum(b["overall"]) / len(b["overall"]) if b["overall"] else None
        mean_latency = sum(b["latency"]) / len(b["latency"]) if b["latency"] else 0
        out[m] = {
            "cells_ok": b["cells_ok"],
            "errors": b["errors"],
            "empty": b["empty"],
            "mean_overall": mean_overall,
            "total_cost_usd": round(b["cost"], 6),
            "mean_latency_ms": int(mean_latency),
        }
    return out


def _read_state() -> dict[str, Any]:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"stage0_models": list(CANDIDATE_MODELS) + list(ANCHOR_MODELS), "survivors": {}}


def _write_state(state: dict[str, Any]) -> None:
    STATE.write_text(json.dumps(state, indent=2))


async def _run_stage(stage: int, models: list[str], slugs: list[str], use_judge: bool) -> dict[str, Any]:
    stage_dir = MM_RUNS / f"stage{stage}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    corpus = yaml.safe_load(CORPUS.read_text())
    by_slug = {e["slug"]: e for e in corpus["urls"]}

    judge = await _judge_provider() if use_judge else None

    sem = asyncio.Semaphore(4)

    async def _cell(model: str, slug: str) -> dict[str, Any]:
        # Idempotency: skip cells with existing meta.json (re-running stage 0
        # after adding new models should NOT re-charge for completed cells).
        existing_meta = stage_dir / _safe(model) / f"{slug}.meta.json"
        existing_score = stage_dir / _safe(model) / f"{slug}.score.json"
        if existing_meta.exists() and (not use_judge or existing_score.exists()):
            try:
                m = json.loads(existing_meta.read_text())
                ans = (stage_dir / _safe(model) / f"{slug}.ans.txt").read_text()
                entry_local = by_slug[slug]
                row: dict[str, Any] = {
                    "model": model,
                    "slug": slug,
                    "class": entry_local.get("class", "?"),
                    **m,
                    "answer_chars": len(ans),
                    "empty": not ans.strip(),
                }
                if existing_score.exists():
                    s = json.loads(existing_score.read_text())
                    row["judge"] = {"overall": s.get("overall"), "reached": s.get("reached")}
                print(f"  [s{stage}] {model:<48} {slug:<22} CACHED", flush=True)
                return row
            except Exception:
                pass  # fall through to fresh run
        async with sem:
            try:
                provider, provider_name = _build_provider_for(model)
            except LLMNotAvailable as exc:
                return {"model": model, "slug": slug, "error": f"provider: {exc}"}
            ex = Extractor(
                provider=provider,
                model=ModelSpec(provider_name, model),
                template=WEBFETCH_DEFAULT_V1,
                max_content_chars=100_000,
                max_tokens=MAX_OUTPUT_TOK,
            )
            entry = by_slug[slug]
            row = await _run_one(model, ex, slug, judge, entry, stage_dir)
            label = (row.get("judge") or {}).get("overall")
            err = row.get("error")
            tag = f"err={err}" if err else f"score={label} tok={row.get('completion_tokens')} ${row.get('cost_usd', 0):.5f}"
            print(f"  [s{stage}] {model:<48} {slug:<22} {tag}", flush=True)
            return row

    t0 = time.time()
    tasks = [_cell(m, s) for m in models for s in slugs]
    rows = await asyncio.gather(*tasks)
    wall = int(time.time() - t0)
    summary = _summarize(rows, stage)
    out = {
        "stage": stage,
        "models": models,
        "slugs": slugs,
        "wall_seconds": wall,
        "n_rows": len(rows),
        "per_model": summary,
        "rows": rows,
    }
    (HERE / f"multi_model_summary_s{stage}.json").write_text(
        json.dumps(out, indent=2, default=str)
    )
    return out


async def _stage0() -> int:
    print("=== Stage 0: smoke (1 URL/model, no judge) ===")
    state = _read_state()
    # Always use the current CANDIDATE_MODELS list (handles roster expansion).
    state["stage0_models"] = list(CANDIDATE_MODELS)
    _write_state(state)
    models = [m for m in CANDIDATE_MODELS if m not in ANCHOR_MODELS]
    result = await _run_stage(0, models, [STAGE0_SLUG], use_judge=False)
    # Survivor rule: at least one non-empty non-error completion
    survivors: list[str] = []
    eliminated: dict[str, str] = {}
    for m, s in result["per_model"].items():
        if s["cells_ok"] > 0 and s["empty"] == 0 and s["errors"] == 0:
            survivors.append(m)
        else:
            eliminated[m] = f"errors={s['errors']} empty={s['empty']} ok={s['cells_ok']}"
    state["survivors"]["stage1"] = survivors
    state["eliminated"] = {**state.get("eliminated", {}), **{m: f"stage0: {r}" for m, r in eliminated.items()}}
    _write_state(state)
    print(f"\nStage 0 done. Survivors → stage 1: {len(survivors)}")
    for m in survivors:
        print(f"  ✓ {m}")
    if eliminated:
        print(f"Eliminated ({len(eliminated)}):")
        for m, r in eliminated.items():
            print(f"  x {m}: {r}")
    return 0


async def _stage1() -> int:
    print("=== Stage 1: ranked subset (5 URLs/model, judged) ===")
    state = _read_state()
    models = state["survivors"].get("stage1") or []
    if not models:
        print("No stage-1 survivors. Run --stage 0 first.")
        return 1
    result = await _run_stage(1, models, STAGE1_SLUGS, use_judge=True)
    # Rank by mean_overall desc, $ asc as tiebreaker. Keep anchors + top 5 OpenRouter
    ranked = sorted(
        result["per_model"].items(),
        key=lambda kv: (
            -(kv[1]["mean_overall"] or 0),
            kv[1]["total_cost_usd"],
        ),
    )
    print("\nStage 1 ranking:")
    print(f"{'rank':<5}{'model':<48}{'mean':>6}{'cost $':>10}{'lat ms':>8}{'errs':>6}")
    for i, (m, s) in enumerate(ranked, 1):
        mo = "—" if s["mean_overall"] is None else f"{s['mean_overall']:.2f}"
        print(f"{i:<5}{m:<48}{mo:>6}{s['total_cost_usd']:>10.4f}{s['mean_latency_ms']:>8}{s['errors']:>6}")

    # Pick top 5 OpenRouter + always keep anchors
    keep: list[str] = [m for m in ranked if False]  # placeholder
    keep = []
    or_count = 0
    for m, s in ranked:
        if m in ANCHOR_MODELS:
            keep.append(m)
        elif or_count < 5 and (s["mean_overall"] or 0) > 0:
            keep.append(m)
            or_count += 1
    state["survivors"]["stage2"] = keep
    _write_state(state)
    print(f"\nKeeping {len(keep)} for stage 2: {keep}")
    return 0


async def _stage2() -> int:
    print("=== Stage 2: full corpus (20 URLs/model, judged) ===")
    state = _read_state()
    models = state["survivors"].get("stage2") or []
    if not models:
        print("No stage-2 survivors. Run --stage 1 first.")
        return 1
    corpus = yaml.safe_load(CORPUS.read_text())
    slugs = [e["slug"] for e in corpus["urls"]]
    await _run_stage(2, models, slugs, use_judge=True)
    print("\nStage 2 complete. See multi_model_summary_s2.json + benchmarks/.../runs/.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=int, required=True, choices=[0, 1, 2])
    args = parser.parse_args()
    fns = {0: _stage0, 1: _stage1, 2: _stage2}
    return asyncio.run(fns[args.stage]())


if __name__ == "__main__":
    sys.exit(main())
