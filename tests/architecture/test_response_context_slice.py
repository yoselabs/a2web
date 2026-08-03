"""The response builder's slice of `FetchContext` is explicit and bounded.

`fetcher_response.py` reads 44 of `FetchContext`'s 74 fields. That
coupling was implicit — nothing stated which fields the response contract
depends on, so `decompose-fetcher-into-files` phase two could not slice
`context.py` per node without first re-deriving the set by hand.

This is the derivation, frozen. It is a LEDGER, not a ban: adding a read is
fine and expected, and the fix is to add the name here. What it prevents is the
set growing silently until "the response builder reads a bit of the context"
quietly means "the response builder reads most of it", which is the state that
makes decomposition impossible to do safely.

**A Protocol was the other option and was not taken.** Declaring 44 members with
real annotations pulls every one of their types into this module's namespace,
which is a large import surface added at the end of a long change for a
property this ledger already gives: the set is stated, and it cannot move
without someone editing it. Worth revisiting when `context.py` is actually
sliced — at that point the Protocol has a consumer.
"""

from __future__ import annotations

import ast
from pathlib import Path

_RESPONSE = Path(__file__).resolve().parents[2] / "src" / "a2web" / "fetcher_response.py"
#: `FetchContext` lives in the tree now (`decompose-fetcher-into-files` §4). Its
#: own module, not the package: this guard parses a class definition, and the
#: package `__init__` only re-exports it.
_FETCHER = Path(__file__).resolve().parents[2] / "src" / "a2web" / "fetcher" / "context.py"

#: Every `fc.<name>` the response builder reads. Frozen 2026-08-01.
_READS: frozenset[str] = frozenset(
    {
        "ask",
        "byline",
        "cache_state",
        "comments_loaded",
        "comments_total",
        "content_candidates",
        "content_md",
        "debug",
        "declared_entity",
        "diagnostics",
        "empty_confirmed",
        "extracted_answer",
        "extraction_meta",
        "extraction_provider_error",
        "extraction_provider_error_retryable",
        "final_url",
        "headings",
        "items_loaded",
        "items_more",
        "items_total",
        "last_gate_outcome",
        "links",
        "meta_dict",
        "next_links_enabled",
        "next_links_handler",
        "next_links_llm",
        "observations",
        "operator_hints",
        "published",
        "record_set",
        # ADR-0009: the caller must be able to tell a live page from an archived
        # copy, so `build_response` reads the snapshot age to emit its hint.
        "snapshot_age_days",
        "snapshot_taken_at",
        "render_requested",
        "requested_url",
        "routing",
        "routing_outcome",
        "small_page_confirmed",
        "small_page_promoted",
        "start_perf",
        "started_at",
        "structured_grounded",
        "terminal",
        "tier_used",
        "title",
        "wrap_content",
    }
)


def _actual_reads() -> set[str]:
    tree = ast.parse(_RESPONSE.read_text(encoding="utf-8"))
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "fc"}


def test_the_context_slice_has_not_grown_silently() -> None:
    actual = _actual_reads()
    assert len(actual) >= 30, f"non-vacuous: found only {len(actual)} `fc.` reads — the AST match broke"

    added = sorted(actual - _READS)
    removed = sorted(_READS - actual)

    assert not added, (
        f"`fetcher_response.py` reads new `FetchContext` field(s): {added}.\n"
        "That is allowed — add them to `_READS`. The ledger exists so the slice "
        "cannot grow to 'most of the context' without anyone noticing, which is "
        "what blocks slicing `context.py` per node."
    )
    assert not removed, (
        f"`_READS` names field(s) the response builder no longer reads: {removed}.\n"
        "Remove them — a ledger with fossils overstates the coupling and makes "
        "the decomposition look harder than it is."
    )


def test_every_read_field_actually_exists_on_the_context() -> None:
    """A read that resolves to nothing would be an AttributeError in production.

    Catches a rename on the `FetchContext` side that this module did not follow —
    the failure the ledger is otherwise blind to, since it only compares the
    module against itself.
    """
    tree = ast.parse(_FETCHER.read_text(encoding="utf-8"))
    cls = next(c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == "FetchContext")
    declared = {n.target.id for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    declared |= {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}

    assert len(declared) >= 50, f"non-vacuous: parsed only {len(declared)} FetchContext members"

    missing = sorted(_actual_reads() - declared)
    assert not missing, f"`fetcher_response.py` reads `fc.<name>` that FetchContext does not declare: {missing}"
