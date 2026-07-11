"""Eval report writer.

Given an `EvalReport`, produces a dated output directory with:

  results.tsv         flat per-row dump for downstream analysis
  manifest.json       run metadata (corpus, systems, judge model, timing)
  leaderboard.md      pivot of system x URL-class — quality + cost
  cost.md             total + per-system + per-URL cost rollup
  findings.md         auto-grouped insights (regressions, ties, blind spots)
  corpus.frozen.yaml  copy of the corpus.yaml used (for reproducibility)

Pure functions: no network, no model calls.
"""

from __future__ import annotations

import csv
import json
import shutil
import statistics
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .runner import EvalReport, EvalRow

_RESULTS_FIELDS = [
    "slug",
    "url",
    "url_class",
    "system",
    "fetch_latency_ms",
    "fetch_cost_usd",
    "fetch_prompt_tokens",
    "fetch_completion_tokens",
    "fetch_error",
    "judge_overall",
    "judge_reached",
    "judge_scores",
    "judge_cost_usd",
    "judge_latency_ms",
    "judge_error",
    "envelope_tokens_total",
    "contract_conformant",
    "contract_conformant_debug",
    "clarity_score",
    "next_links_score",
]


def write_all(report: EvalReport) -> None:
    """Write every output artifact under `report.output_dir`."""
    report.output_dir.mkdir(parents=True, exist_ok=True)

    _write_results_tsv(report)
    _write_results_json(report)
    _write_manifest(report)
    _write_leaderboard(report)
    _write_axes(report)
    _write_cost(report)
    _write_findings(report)
    _copy_corpus(report)


def _cost_token_summary(rows: list[EvalRow]) -> dict[str, object]:
    """Roll up a run's spend — the numbers the provider (claude-code SDK on the
    subscription path) already reported. `total_cost_usd` covers fetch + judge;
    token totals are fetch-side (judge tokens are not retained per row)."""
    return {
        "cells": len(rows),
        "total_cost_usd": round(sum(r.fetch_cost_usd + r.judge_cost_usd for r in rows), 6),
        "fetch_prompt_tokens": sum(r.fetch_prompt_tokens for r in rows),
        "fetch_completion_tokens": sum(r.fetch_completion_tokens for r in rows),
    }


def _write_results_json(report: EvalReport) -> None:
    """Structured `{summary, rows}` — a run's every result plus its cost/token
    rollup, legible to any downstream tool without parsing the markdown."""
    rows = [
        {
            "slug": r.slug,
            "url": r.url,
            "class": r.url_class,
            "system": r.system,
            "task": r.task,
            "provider": r.provider,
            "quality": r.judge_overall,
            "reached": r.judge_reached,
            "clarity": r.clarity_score,
            "contract_ok": r.contract_conformant,
            "next_links_score": r.next_links_score,
            "envelope_tokens_total": r.envelope_tokens_total,
            "fetch_cost_usd": r.fetch_cost_usd,
            "fetch_prompt_tokens": r.fetch_prompt_tokens,
            "fetch_completion_tokens": r.fetch_completion_tokens,
            "judge_cost_usd": r.judge_cost_usd,
            "fetch_error": r.fetch_error,
        }
        for r in report.rows
    ]
    per_system: dict[str, list[EvalRow]] = {}
    for r in report.rows:
        per_system.setdefault(r.system, []).append(r)
    payload = {
        "summary": {
            "overall": _cost_token_summary(report.rows),
            "per_system": {system: _cost_token_summary(rs) for system, rs in per_system.items()},
        },
        "rows": rows,
    }
    (report.output_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n")


def _write_results_tsv(report: EvalReport) -> None:
    path = report.output_dir / "results.tsv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_RESULTS_FIELDS, delimiter="\t")
        w.writeheader()
        for row in report.rows:
            w.writerow(
                {
                    "slug": row.slug,
                    "url": row.url,
                    "url_class": row.url_class,
                    "system": row.system,
                    "fetch_latency_ms": row.fetch_latency_ms,
                    "fetch_cost_usd": f"{row.fetch_cost_usd:.6f}",
                    "fetch_prompt_tokens": row.fetch_prompt_tokens,
                    "fetch_completion_tokens": row.fetch_completion_tokens,
                    "fetch_error": row.fetch_error or "",
                    "judge_overall": row.judge_overall if row.judge_overall is not None else "",
                    "judge_reached": row.judge_reached if row.judge_reached is not None else "",
                    "judge_scores": ",".join(str(s) for s in (row.judge_scores or [])),
                    "judge_cost_usd": f"{row.judge_cost_usd:.6f}",
                    "judge_latency_ms": row.judge_latency_ms,
                    "judge_error": row.judge_error or "",
                    "envelope_tokens_total": row.envelope_tokens_total,
                    "contract_conformant": "" if row.contract_conformant is None else row.contract_conformant,
                    "contract_conformant_debug": ("" if row.contract_conformant_debug is None else row.contract_conformant_debug),
                    "clarity_score": row.clarity_score if row.clarity_score is not None else "",
                    "next_links_score": row.next_links_score if row.next_links_score is not None else "",
                }
            )


def _write_manifest(report: EvalReport) -> None:
    path = report.output_dir / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "corpus_path": report.corpus_path,
                "systems": report.systems,
                "provider": report.provider,
                "judge_model": report.judge_model,
                "bench_judge_model": report.bench_judge_model,
                "started_at": report.started_at.isoformat(),
                "ended_at": report.ended_at.isoformat(),
                "wall_seconds": report.wall_seconds,
                "row_count": len(report.rows),
            },
            indent=2,
            default=str,
        )
    )


def _write_leaderboard(report: EvalReport) -> None:
    """Mean + median judge_overall per system, plus per-URL-class breakdown."""
    by_system: dict[str, list[int]] = defaultdict(list)
    by_class_system: dict[tuple[str, str], list[int]] = defaultdict(list)
    reached_by_system: dict[str, list[bool]] = defaultdict(list)

    for row in report.rows:
        if row.judge_overall is not None:
            by_system[row.system].append(row.judge_overall)
            by_class_system[(row.url_class or "?", row.system)].append(row.judge_overall)
        if row.judge_reached is not None:
            reached_by_system[row.system].append(row.judge_reached)

    lines: list[str] = ["# Leaderboard\n"]
    lines.append("## Overall\n")
    lines.append("| System | n | reached | mean | median | min | max |")
    lines.append("|---|---|---|---|---|---|---|")
    for system in report.systems:
        scores = by_system.get(system, [])
        if not scores:
            lines.append(f"| {system} | 0 | — | — | — | — | — |")
            continue
        reached = reached_by_system.get(system, [])
        reached_pct = f"{sum(1 for r in reached if r)}/{len(reached)}" if reached else "—"
        mean_s = statistics.mean(scores)
        median_s = statistics.median(scores)
        lines.append(f"| {system} | {len(scores)} | {reached_pct} | {mean_s:.2f} | {median_s:.1f} | {min(scores)} | {max(scores)} |")
    lines.append("")

    # Per URL class
    classes = sorted({c for (c, _s) in by_class_system})
    if classes:
        lines.append("## By URL class (mean judge_overall)\n")
        header = "| Class | " + " | ".join(report.systems) + " |"
        sep = "|---" * (len(report.systems) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for cls in classes:
            cells = []
            for system in report.systems:
                scores = by_class_system.get((cls, system), [])
                cells.append(f"{statistics.mean(scores):.2f}" if scores else "—")
            lines.append(f"| {cls} | " + " | ".join(cells) + " |")
        lines.append("")

    (report.output_dir / "leaderboard.md").write_text("\n".join(lines))


def _mean_opt(values: Iterable[float]) -> float | None:
    """Mean of a value list, or None when empty."""
    vals = list(values)
    return statistics.mean(vals) if vals else None


def _fmt(value: float | None, places: int = 2) -> str:
    return f"{value:.{places}f}" if value is not None else "—"


def _delta(value: float | None, base: float | None) -> str:
    """Signed a2web-minus-baseline delta, '—' when either side is missing."""
    if value is None or base is None:
        return "—"
    diff = value - base
    sign = "+" if diff >= 0 else ""
    places = 0 if abs(diff) >= 10 else 2
    return f"{sign}{diff:.{places}f}"


def _write_axes(report: EvalReport) -> None:
    """Per-system four-axis table + a vs-WebFetch delta summary."""
    lines: list[str] = ["# Output benchmark — four axes\n"]
    lines.append(
        "Axes: **answer quality** (judge 0-5), **token cost** (tokens of the "
        "response envelope the agent reads), **output clarity** (judge 0-5), "
        "**data-contract conformance** (deterministic envelope check). The "
        "`next_links` axis is scored on listing URLs only.\n"
    )

    lines.append("## Per system\n")
    lines.append("| System | n | quality | env tokens | clarity | contract ok | next_links (n) |")
    lines.append("|---|---|---|---|---|---|---|")
    agg: dict[str, dict[str, float | None]] = {}
    for system in report.systems:
        rows = [r for r in report.rows if r.system == system]
        quality = _mean_opt([r.judge_overall for r in rows if r.judge_overall is not None])
        tokens = _mean_opt([r.envelope_tokens_total for r in rows if r.envelope_tokens_total])
        clarity = _mean_opt([r.clarity_score for r in rows if r.clarity_score is not None])
        contract_rows = [r for r in rows if r.contract_conformant is not None]
        contract_ok = sum(1 for r in contract_rows if r.contract_conformant)
        nl_rows = [r for r in rows if r.next_links_score is not None]
        nl_mean = _mean_opt([r.next_links_score for r in rows if r.next_links_score is not None])
        agg[system] = {"quality": quality, "tokens": tokens, "clarity": clarity}
        contract_cell = f"{contract_ok}/{len(contract_rows)}" if contract_rows else "—"
        nl_cell = f"{_fmt(nl_mean)} ({len(nl_rows)})" if nl_rows else "—"
        tok_cell = _fmt(tokens, 0) if tokens is not None else "—"
        lines.append(f"| {system} | {len(rows)} | {_fmt(quality)} | {tok_cell} | {_fmt(clarity)} | {contract_cell} | {nl_cell} |")
    lines.append("")

    baseline = "webfetch_baseline"
    if baseline in agg:
        base = agg[baseline]
        lines.append("## vs WebFetch baseline\n")
        lines.append("Delta = a2web system minus WebFetch. Quality / clarity: higher is better. Env tokens: lower is better.\n")
        lines.append("| System | Δ quality | Δ env tokens | Δ clarity |")
        lines.append("|---|---|---|---|")
        for system in report.systems:
            if system == baseline:
                continue
            sys_agg = agg[system]
            lines.append(
                f"| {system} | {_delta(sys_agg['quality'], base['quality'])} "
                f"| {_delta(sys_agg['tokens'], base['tokens'])} "
                f"| {_delta(sys_agg['clarity'], base['clarity'])} |"
            )
        lines.append("")

    violators = [r for r in report.rows if r.contract_conformant is False or r.contract_conformant_debug is False]
    if violators:
        lines.append(f"## Data-contract violations ({len(violators)} rows)\n")
        for r in violators[:20]:
            viols = r.contract_violations + r.contract_violations_debug
            lines.append(f"- `{r.slug}` x `{r.system}` — {'; '.join(viols)}")
        if len(violators) > 20:
            lines.append(f"- … and {len(violators) - 20} more")
        lines.append("")

    (report.output_dir / "axes.md").write_text("\n".join(lines))


def _write_cost(report: EvalReport) -> None:
    """Total + per-system + cost-per-quality-point."""
    fetch_cost: dict[str, float] = defaultdict(float)
    judge_cost: dict[str, float] = defaultdict(float)
    scores: dict[str, list[int]] = defaultdict(list)
    for row in report.rows:
        fetch_cost[row.system] += row.fetch_cost_usd
        judge_cost[row.system] += row.judge_cost_usd
        if row.judge_overall is not None:
            scores[row.system].append(row.judge_overall)

    total_fetch = sum(fetch_cost.values())
    total_judge = sum(judge_cost.values())
    total = total_fetch + total_judge

    lines: list[str] = ["# Cost\n"]
    lines.append(f"- Total: **${total:.4f}** (fetch ${total_fetch:.4f} + judge ${total_judge:.4f})")
    lines.append(f"- Rows: {len(report.rows)}")
    if report.rows:
        lines.append(f"- Cost per row: ${total / len(report.rows):.6f}")
    lines.append("")
    lines.append("## Per system\n")
    lines.append("| System | fetch $ | judge $ | total $ | mean score | $/score-point |")
    lines.append("|---|---|---|---|---|---|")
    for system in report.systems:
        s = scores.get(system, [])
        total_sys = fetch_cost[system] + judge_cost[system]
        mean_score = statistics.mean(s) if s else 0.0
        cost_per_point = total_sys / mean_score if mean_score > 0 else float("inf")
        cost_per_point_s = f"${cost_per_point:.4f}" if mean_score > 0 else "—"
        fc = fetch_cost[system]
        jc = judge_cost[system]
        lines.append(f"| {system} | ${fc:.4f} | ${jc:.4f} | ${total_sys:.4f} | {mean_score:.2f} | {cost_per_point_s} |")
    (report.output_dir / "cost.md").write_text("\n".join(lines) + "\n")


def _write_findings(report: EvalReport) -> None:
    """Auto-grouped insights — winners, losers, system x URL-class outliers."""
    lines: list[str] = ["# Findings\n"]

    # System reach summary
    lines.append("## Reach (judge said real content delivered)\n")
    for system in report.systems:
        reached = sum(1 for r in report.rows if r.system == system and r.judge_reached)
        total = sum(1 for r in report.rows if r.system == system)
        lines.append(f"- **{system}**: {reached}/{total}")
    lines.append("")

    # Per-URL winners
    by_slug: dict[str, list[EvalRow]] = defaultdict(list)
    for row in report.rows:
        by_slug[row.slug].append(row)
    won_by: dict[str, int] = defaultdict(int)
    for rows in by_slug.values():
        scored = [r for r in rows if r.judge_overall is not None]
        if not scored:
            continue
        best = max(r.judge_overall for r in scored)  # type: ignore[type-var]
        winners = [r.system for r in scored if r.judge_overall == best]
        for w in winners:
            won_by[w] += 1
    if won_by:
        lines.append("## Per-URL wins (tied wins count for each)\n")
        for system, n in sorted(won_by.items(), key=lambda kv: -kv[1]):
            lines.append(f"- **{system}**: {n}")
        lines.append("")

    # Errors
    fetch_errors = [r for r in report.rows if r.fetch_error]
    judge_errors = [r for r in report.rows if r.judge_error]
    if fetch_errors:
        lines.append(f"## Fetch errors ({len(fetch_errors)} rows)\n")
        for r in fetch_errors[:20]:
            lines.append(f"- `{r.slug}` x `{r.system}` — {r.fetch_error}")
        if len(fetch_errors) > 20:
            lines.append(f"- … and {len(fetch_errors) - 20} more")
        lines.append("")
    if judge_errors:
        lines.append(f"## Judge errors ({len(judge_errors)} rows)\n")
        for r in judge_errors[:20]:
            lines.append(f"- `{r.slug}` x `{r.system}` — {r.judge_error}")
        if len(judge_errors) > 20:
            lines.append(f"- … and {len(judge_errors) - 20} more")
        lines.append("")

    (report.output_dir / "findings.md").write_text("\n".join(lines))


def _copy_corpus(report: EvalReport) -> None:
    src = Path(report.corpus_path)
    if src.is_file():
        shutil.copyfile(src, report.output_dir / "corpus.frozen.yaml")


def stats_dict(report: EvalReport) -> dict[str, Any]:
    """Headline metrics suitable for log lines / CI artifacts — the four axes
    per system plus cost and timing."""
    by_system_overall: dict[str, list[int]] = defaultdict(list)
    cost_by_system: dict[str, float] = defaultdict(float)
    tokens_by_system: dict[str, list[int]] = defaultdict(list)
    clarity_by_system: dict[str, list[int]] = defaultdict(list)
    next_links_by_system: dict[str, list[int]] = defaultdict(list)
    contract_by_system: dict[str, list[bool]] = defaultdict(list)
    for row in report.rows:
        if row.judge_overall is not None:
            by_system_overall[row.system].append(row.judge_overall)
        cost_by_system[row.system] += row.fetch_cost_usd + row.judge_cost_usd
        if row.envelope_tokens_total:
            tokens_by_system[row.system].append(row.envelope_tokens_total)
        if row.clarity_score is not None:
            clarity_by_system[row.system].append(row.clarity_score)
        if row.next_links_score is not None:
            next_links_by_system[row.system].append(row.next_links_score)
        if row.contract_conformant is not None:
            contract_by_system[row.system].append(row.contract_conformant)

    def _means(buckets: dict[str, list[int]]) -> dict[str, float | None]:
        return {s: (statistics.mean(v) if v else None) for s, v in buckets.items()}

    return {
        "rows": len(report.rows),
        "systems": report.systems,
        "mean_overall_by_system": _means(by_system_overall),
        "mean_envelope_tokens_by_system": _means(tokens_by_system),
        "mean_clarity_by_system": _means(clarity_by_system),
        "mean_next_links_by_system": _means(next_links_by_system),
        "contract_pass_by_system": {s: f"{sum(1 for c in v if c)}/{len(v)}" for s, v in contract_by_system.items()},
        "cost_by_system_usd": dict(cost_by_system),
        "total_cost_usd": sum(cost_by_system.values()),
        "wall_seconds": report.wall_seconds,
    }


__all__ = ["stats_dict", "write_all"]
