"""Browser-backend bake-off — render-layer comparison (Phase A).

TRANSIENT (browser-backend-bakeoff §3): drives a browser-stress URL set through
each candidate backend and scores the three primary axes *at the render layer*,
so it costs live browser renders but ~no LLM quota:

  - SPA-read success — did we capture usable markdown (block_detector verdict
    `ok`, i.e. real content above the length floor)?
  - robustness       — did we survive (not a block/anti-bot page)?
  - speed            — wall_ms per render.

LLM answer-quality (Phase B) runs separately, only on the render-layer
winner(s), to keep quota to ~1 backend instead of (backends x urls).

Run:  uv run python -m a2web.llm_eval.browser_bakeoff
Writes a table to stdout and (with --write) to eval/findings_<date>.md.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
from dataclasses import dataclass

from a2web.packages.block_detector import LENGTH_FLOOR, BlockVerdict, evaluate
from a2web.packages.browser_backends import RenderOutcome
from a2web.packages.content_extract import extract_markdown
from a2web.settings import AppSettings
from a2web.state import select_backend

# Browser-stress set (browser-backend-bakeoff §3): URLs that actually force the
# browser tier — TR e-commerce SPAs (the Trendyol incident class), a heavy JS
# docs SPA, and a bot-detection robustness probe. (slug, url, js_heavy).
STRESS_URLS: tuple[tuple[str, str, bool], ...] = (
    ("trendyol-search", "https://www.trendyol.com/sr?q=laptop", True),
    ("hepsiburada-search", "https://www.hepsiburada.com/ara?q=laptop", True),
    ("react-dev", "https://react.dev/", True),
    ("vercel", "https://vercel.com/", True),
    ("nowsecure-cf", "https://nowsecure.nl/", False),
)

# The bake-off scored three candidates (patchright, rebrowser, zendriver) — see
# eval/findings_2026-06-27.md. rebrowser lost and was pruned, so re-runs cover
# only the two retained engines (its manifest no longer registers).
CANDIDATES = ("patchright", "zendriver")
_BLOCKED = {BlockVerdict.block_page_detected, BlockVerdict.anti_bot}


@dataclass(slots=True)
class Cell:
    backend: str
    slug: str
    outcome: str
    html_bytes: int
    md_len: int
    verdict: str
    read_ok: bool
    survived: bool
    wall_ms: int
    detail: str = ""


async def _run_cell(backend_name: str, slug: str, url: str, js_heavy: bool, budget_s: float) -> Cell:
    backend = select_backend(AppSettings(browser_backend=backend_name))
    async with backend:
        page = await backend.render(url, cookies=[], budget_s=budget_s, js_heavy=js_heavy)
    if page.outcome is not RenderOutcome.ok:
        return Cell(backend_name, slug, page.outcome.value, len(page.html), 0, "-", False, False, page.wall_ms, page.detail)
    extracted = await extract_markdown(page.html, url)
    md = extracted.content_md or ""
    block = evaluate(content_md=md, raw_html=page.html, content_type="text/html")
    verdict = block.verdict
    read_ok = verdict is BlockVerdict.ok and len(md) >= LENGTH_FLOOR
    survived = verdict not in _BLOCKED
    return Cell(backend_name, slug, "ok", len(page.html), len(md), verdict.value, read_ok, survived, page.wall_ms)


async def run(budget_s: float = 25.0) -> list[Cell]:
    cells: list[Cell] = []
    for backend_name in CANDIDATES:
        for slug, url, js_heavy in STRESS_URLS:
            try:
                cell = await _run_cell(backend_name, slug, url, js_heavy, budget_s)
            except Exception as exc:  # harness-level failure — record, keep going
                cell = Cell(backend_name, slug, "harness_error", 0, 0, "-", False, False, 0, f"{type(exc).__name__}: {exc}")
            print(
                f"  {backend_name:11} {slug:18} {cell.outcome:14} "
                f"read_ok={cell.read_ok!s:5} survived={cell.survived!s:5} {cell.wall_ms:6}ms md={cell.md_len}"
            )
            cells.append(cell)
    return cells


def _summary(cells: list[Cell]) -> list[tuple[str, int, int, int]]:
    """Per-backend: (backend, read_ok_count, survived_count, median_wall_ms over ok)."""
    rows: list[tuple[str, int, int, int]] = []
    for backend_name in CANDIDATES:
        mine = [c for c in cells if c.backend == backend_name]
        read_ok = sum(c.read_ok for c in mine)
        survived = sum(c.survived for c in mine)
        ok_ms = [c.wall_ms for c in mine if c.outcome == "ok"]
        median_ms = int(statistics.median(ok_ms)) if ok_ms else 0
        rows.append((backend_name, read_ok, survived, median_ms))
    return rows


def _render_markdown(cells: list[Cell], summary: list[tuple[str, int, int, int]]) -> str:
    n = len(STRESS_URLS)
    lines = [
        "# Browser-backend bake-off — render-layer findings (Phase A)",
        "",
        f"Date: 2026-06-27 - {len(CANDIDATES)} backends x {n} browser-stress URLs - render-layer only (~0 LLM quota).",
        "",
        "## Ranking (primary axes)",
        "",
        "| backend | SPA-read ok | survived | median ok wall |",
        "|---|---|---|---|",
    ]
    for backend_name, read_ok, survived, median_ms in summary:
        lines.append(f"| {backend_name} | {read_ok}/{n} | {survived}/{n} | {median_ms} ms |")
    header = "| backend | url | outcome | verdict | read_ok | survived | wall_ms | md_len | detail |"
    lines += ["", "## Per-cell", "", header, "|---|---|---|---|---|---|---|---|---|"]
    for c in cells:
        cols = [c.backend, c.slug, c.outcome, c.verdict, str(c.read_ok), str(c.survived), str(c.wall_ms), str(c.md_len), c.detail[:60]]
        lines.append("| " + " | ".join(cols) + " |")
    note = "- Phase B (LLM answer-quality on the winner) recorded separately once the render-layer winner is chosen."
    lines += ["", "## Notes", "", note, ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=25.0)
    parser.add_argument("--write", action="store_true", help="write eval/findings_2026-06-27.md")
    args = parser.parse_args()
    print(f"Bake-off: {len(CANDIDATES)} backends x {len(STRESS_URLS)} URLs (budget={args.budget}s)\n")
    cells = asyncio.run(run(args.budget))
    summary = _summary(cells)
    print("\n=== ranking ===")
    for backend_name, read_ok, survived, median_ms in summary:
        print(f"  {backend_name:11} read_ok={read_ok}/{len(STRESS_URLS)} survived={survived}/{len(STRESS_URLS)} median={median_ms}ms")
    md = _render_markdown(cells, summary)
    if args.write:
        from pathlib import Path

        path = Path("eval/findings_2026-06-27.md")
        path.write_text(md)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
